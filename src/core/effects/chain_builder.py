"""效果器链构建器 / Effects Chain Builder.

编排三个估算器, 生成完整的效果器分析结果。
同时负责从预设参数合成干音参考音频。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np

from src.config.settings import EffectsSettings
from src.core.effects.types import (
    EffectsProfile,
    EQEstimate,
    ReverbEstimate,
    CompressionEstimate,
)
from src.core.effects.eq_estimator import EQEstimator
from src.core.effects.reverb_estimator import ReverbEstimator
from src.core.effects.dynamics_estimator import DynamicsEstimator

logger = logging.getLogger(__name__)


class EffectsChainBuilder:
    """效果器链构建器 / Effects chain builder.

    编排 EQ / Reverb / Compression 三个估算器,
    将结果组装为 EffectsProfile 并输出 JSON。

    用法:
        builder = EffectsChainBuilder(settings)
        dry_audio = builder.synthesize_dry_reference(preset, duration, sr)
        profile = builder.estimate_all(dry_audio, wet_audio, sr, "piano", "Grand Piano")
    """

    def __init__(self, settings: EffectsSettings | None = None):
        """初始化效果器链构建器.

        Args:
            settings: 效果器设置
        """
        self.settings = settings or EffectsSettings()
        self.eq_estimator = EQEstimator(self.settings)
        self.reverb_estimator = ReverbEstimator(self.settings)
        self.dynamics_estimator = DynamicsEstimator(self.settings)

    # ===== 主接口 =====

    def estimate_all(
        self,
        dry_audio: np.ndarray,
        wet_audio: np.ndarray,
        sr: int,
        stem_name: str = "",
        preset_name: str = "",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> EffectsProfile:
        """运行完整效果器分析 / Run full effects analysis.

        Args:
            dry_audio: 干音参考音频
            wet_audio: 湿音 stem 音频
            sr: 采样率
            stem_name: 乐器名
            preset_name: 匹配到的预设名
            progress_callback: 进度回调

        Returns:
            EffectsProfile 包含所有效果器参数
        """
        profile = EffectsProfile(
            stem_name=stem_name,
            preset_name=preset_name,
        )

        total_stages = 3
        stage_base = 0

        # --- Stage 1: EQ (0-33%) ---
        self._report(progress_callback, stage_base, "估算 EQ 参数…")
        try:
            profile.eq = self.eq_estimator.estimate(
                dry_audio, wet_audio, sr,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(stage_base + p / total_stages),
                    f"[EQ] {m}",
                ),
            )
        except Exception as e:
            logger.warning(f"EQ 估算失败: {e}")
            profile.eq = EQEstimate()

        stage_base += 33

        # --- Stage 2: Reverb (33-66%) ---
        self._report(progress_callback, stage_base, "估算混响参数…")
        try:
            profile.reverb = self.reverb_estimator.estimate(
                dry_audio, wet_audio, sr,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(stage_base + p / total_stages),
                    f"[Reverb] {m}",
                ),
            )
        except Exception as e:
            logger.warning(f"混响估算失败: {e}")
            profile.reverb = ReverbEstimate()

        stage_base += 33

        # --- Stage 3: Compression (66-100%) ---
        self._report(progress_callback, stage_base, "估算压缩参数…")
        try:
            profile.compression = self.dynamics_estimator.estimate(
                dry_audio, wet_audio, sr,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(stage_base + p / total_stages),
                    f"[Comp] {m}",
                ),
            )
        except Exception as e:
            logger.warning(f"压缩估算失败: {e}")
            profile.compression = CompressionEstimate()

        # 计算置信度
        profile.confidence = self._compute_confidence(profile)

        self._report(progress_callback, 100, "效果器分析完成")
        return profile

    # ===== 干音参考合成 =====

    def synthesize_dry_reference(
        self,
        preset,  # Preset 对象 (避免循环导入)
        duration_sec: float = 3.0,
        sr: int = 44100,
        midi_note: int = 60,  # 中央 C
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> np.ndarray:
        """从预设参数合成干音参考音频 / Synthesize dry reference from preset params.

        使用预设的 perceptual params (brightness/warmth/attack/sustain/body)
        生成一段简短的合成音色, 用于和湿音 stem 对比。

        Args:
            preset: Preset 对象
            duration_sec: 合成时长 (秒)
            sr: 采样率
            midi_note: MIDI 音符号 (默认中央 C=60)
            progress_callback: 进度回调

        Returns:
            合成音频数组 (1D, float32)
        """
        self._report(progress_callback, 0, "合成干音参考…")

        params = preset.params
        brightness = params.get("brightness", 0.5)
        warmth = params.get("warmth", 0.5)
        attack = params.get("attack", 0.3)
        sustain = params.get("sustain", 0.5)
        body = params.get("body", 0.5)
        instrument = getattr(preset, "instrument", "piano")

        # 1. 选择基础波形
        waveform = self._choose_waveform(instrument, body)

        # 2. 生成基频信号
        freq = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
        total_samples = int(duration_sec * sr)
        t = np.arange(total_samples, dtype=np.float64) / sr

        # 使用 pedalboard 生成合成音 (如果有的话)
        # 降级方案: 简单的加法合成
        try:
            audio = self._synthesize_basic_tone(
                waveform, freq, t, sr,
                brightness=brightness,
                warmth=warmth,
                body=body,
            )
        except Exception:
            # 最简 fallback: 纯正弦波
            audio = np.sin(2.0 * np.pi * freq * t).astype(np.float64)
            audio *= 0.5

        self._report(progress_callback, 30, "应用 ADSR 包络…")

        # 3. 应用 ADSR 包络 (基于 attack/sustain 参数)
        audio = self._apply_adsr(audio, sr, attack, sustain)

        self._report(progress_callback, 60, "应用音色整形 (EQ)…")

        # 4. 音色整形: 基于 brightness/warmth 做 EQ
        audio = self._apply_timbre_eq(audio, sr, brightness, warmth)

        self._report(progress_callback, 90, "归一化…")

        # 5. 归一化并转为 float32
        peak = np.max(np.abs(audio)) + 1e-10
        audio = audio / peak * 0.8

        self._report(progress_callback, 100, "干音合成完成")

        return audio.astype(np.float32)

    # ===== 内部方法 =====

    def _choose_waveform(self, instrument: str, body: float) -> str:
        """根据乐器类型选择基础波形 / Choose base waveform by instrument.

        Args:
            instrument: 乐器类型
            body: 饱满度参数 (影响泛音丰富度)

        Returns:
            波形类型: 'sine' | 'triangle' | 'saw' | 'square'
        """
        if instrument == "piano":
            return "triangle" if body > 0.6 else "sine"
        elif instrument == "guitar":
            return "triangle"
        elif instrument == "bass":
            return "saw" if body > 0.5 else "sine"
        elif instrument == "synth":
            return "saw" if body > 0.7 else "square"
        else:
            return "triangle"

    def _synthesize_basic_tone(
        self,
        waveform: str,
        freq: float,
        t: np.ndarray,
        sr: int,
        brightness: float = 0.5,
        warmth: float = 0.5,
        body: float = 0.5,
    ) -> np.ndarray:
        """基础加法合成 / Basic additive synthesis.

        Args:
            waveform: 基础波形类型
            freq: 基频
            t: 时间轴
            sr: 采样率
            brightness: 亮度 (影响高次谐波)
            warmth: 温暖度 (影响低频谐波)
            body: 饱满度 (影响泛音数量)

        Returns:
            合成音频
        """
        audio = np.zeros_like(t, dtype=np.float64)

        # 谐波数量: body 越高, 泛音越多
        n_harmonics = int(3 + body * 8)  # 3-11 个泛音

        for h in range(1, n_harmonics + 1):
            h_freq = freq * h
            # 基频幅度根据波形衰减
            if waveform == "sine":
                if h == 1:
                    amplitude = 1.0
                else:
                    amplitude = 0.0
            elif waveform == "triangle":
                amplitude = 1.0 / (h**2) if h % 2 == 1 else 0.0
            elif waveform == "saw":
                amplitude = 1.0 / h
            elif waveform == "square":
                amplitude = 1.0 / h if h % 2 == 1 else 0.0
            else:
                amplitude = 1.0 / h

            # brightness 影响高频谐波权重
            if h > 5:
                amplitude *= brightness * 1.5
            # warmth 影响中低频谐波权重
            if 2 <= h <= 5:
                amplitude *= warmth * 1.2

            audio += amplitude * np.sin(2.0 * np.pi * h_freq * t)

        return audio

    def _apply_adsr(
        self,
        audio: np.ndarray,
        sr: int,
        attack: float,
        sustain: float,
    ) -> np.ndarray:
        """应用简化的 ADSR 包络 / Apply simplified ADSR envelope.

        Args:
            audio: 音频数据
            sr: 采样率
            attack: 起音参数 (0-1, 越小=起音越快)
            sustain: 延音参数 (0-1, 越小=衰减越快)

        Returns:
            应用包络后的音频
        """
        n = len(audio)
        if n < 2:
            return audio

        env = np.ones(n, dtype=np.float64)

        # Attack 阶段: 0 → 1
        attack_samples = int(max(attack * 0.5, 0.005) * sr)  # 5-500ms
        attack_samples = max(attack_samples, int(0.001 * sr))  # 最少 1ms
        attack_samples = min(attack_samples, n // 3)

        if attack_samples > 1:
            env[:attack_samples] = np.linspace(0.0, 1.0, attack_samples)

        # Decay 阶段: 1 → sustain_level
        sustain_level = 0.3 + sustain * 0.5  # 0.3-0.8
        decay_start = attack_samples
        decay_samples = int(0.15 * sr)  # 150ms decay
        decay_end = min(decay_start + decay_samples, n)

        if decay_end > decay_start:
            env[decay_start:decay_end] = np.linspace(1.0, sustain_level, decay_end - decay_start)

        # Sustain 阶段: 保持不变
        # Release 阶段: sustain_level → 0 (最后 10%)
        release_samples = int(0.2 * n)  # 最后 20%
        release_start = max(decay_end, n - release_samples)

        if release_start < n - 1:
            env[release_start:] = np.linspace(sustain_level, 0.0, n - release_start)

        return audio * env

    def _apply_timbre_eq(
        self,
        audio: np.ndarray,
        sr: int,
        brightness: float,
        warmth: float,
    ) -> np.ndarray:
        """应用音色 EQ 整形 / Apply timbre EQ shaping.

        Args:
            audio: 音频数据
            sr: 采样率
            brightness: 亮度 (增强高频)
            warmth: 温暖度 (增强低频)

        Returns:
            EQ 后的音频
        """
        try:
            import pedalboard

            # 使用 pedalboard 的 EQ 进行音色整形
            # 低架: warmth (100-300Hz)
            # 高架: brightness (3-8kHz)
            low_gain = (warmth - 0.5) * 6.0  # -3 to +3 dB
            high_gain = (brightness - 0.5) * 8.0  # -4 to +4 dB

            board = pedalboard.Pedalboard([
                pedalboard.HighpassFilter(cutoff_frequency_hz=20.0),
                pedalboard.LowShelfFilter(
                    cutoff_frequency_hz=250.0,
                    gain_db=low_gain,
                    q=0.7,
                ),
                pedalboard.HighShelfFilter(
                    cutoff_frequency_hz=5000.0,
                    gain_db=high_gain,
                    q=0.7,
                ),
            ])
            return board(audio, sr)

        except ImportError:
            # Fallback: 简单的 biquad 实现
            return self._simple_shelf_eq(audio, sr, brightness, warmth)

    def _simple_shelf_eq(
        self,
        audio: np.ndarray,
        sr: int,
        brightness: float,
        warmth: float,
    ) -> np.ndarray:
        """简单的高低架 EQ (无 pedalboard 时的 fallback) / Simple shelf EQ fallback.

        Args:
            audio: 音频数据
            sr: 采样率
            brightness: 亮度
            warmth: 温暖度

        Returns:
            EQ 后的音频
        """
        from scipy.signal import butter, sosfilt

        result = audio.copy()
        sos_list = []

        # 低架: 增强或衰减 250Hz 以下
        low_gain = (warmth - 0.5) * 6.0
        if abs(low_gain) > 0.5:
            try:
                if low_gain > 0:
                    # boost: 低通 + 混合
                    sos = butter(2, 250.0 / (sr / 2), btype="low", output="sos")
                    low_pass = sosfilt(sos, result)
                    result = result + low_pass * (10.0**(low_gain/20.0) - 1.0)
                else:
                    # cut: 使用低架
                    sos = butter(2, 250.0 / (sr / 2), btype="low", output="sos")
                    low_pass = sosfilt(sos, result)
                    result = result - low_pass * (1.0 - 10.0**(low_gain/20.0))
            except Exception:
                pass

        # 高架: 增强或衰减 5kHz 以上
        high_gain = (brightness - 0.5) * 8.0
        if abs(high_gain) > 0.5:
            try:
                if high_gain > 0:
                    sos = butter(2, 5000.0 / (sr / 2), btype="high", output="sos")
                    high_pass = sosfilt(sos, result)
                    result = result + high_pass * (10.0**(high_gain/20.0) - 1.0)
                else:
                    sos = butter(2, 5000.0 / (sr / 2), btype="high", output="sos")
                    high_pass = sosfilt(sos, result)
                    result = result - high_pass * (1.0 - 10.0**(high_gain/20.0))
            except Exception:
                pass

        return result

    def _compute_confidence(self, profile: EffectsProfile) -> float:
        """计算估算结果的置信度 / Compute confidence score.

        Args:
            profile: 效果器分析结果

        Returns:
            置信度 (0-1)
        """
        conf = 0.5  # baseline

        # EQ: 有频段则增加信心
        if profile.eq and profile.eq.bands:
            conf += min(len(profile.eq.bands) * 0.1, 0.3)

        # Reverb: RT60 在合理范围内增加信心
        if profile.reverb and 0.1 < profile.reverb.rt60_sec < 5.0:
            conf += 0.1

        # Compression: ratio > 1.2 说明检测到压缩
        if profile.compression and profile.compression.ratio > 1.2:
            conf += 0.1

        return float(np.clip(conf, 0.0, 1.0))

    @staticmethod
    def _report(
        callback: Callable[[int, str], None] | None,
        pct: int,
        msg: str,
    ) -> None:
        """安全的进度回调 / Safe progress callback."""
        if callback:
            try:
                callback(pct, msg)
            except Exception:
                pass
