"""混响参数估算器 / Reverb Parameter Estimator.

通过分析音频的能量衰减曲线 (EDC) 和早期/后期能量比,
估算 RT60 混响时间和干湿比。
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from src.config.settings import EffectsSettings
from src.core.effects.types import ReverbEstimate

logger = logging.getLogger(__name__)


class ReverbEstimator:
    """混响参数估算器 / Reverb parameter estimator.

    使用 Schroeder 反向积分法计算能量衰减曲线 (EDC),
    线性拟合衰减斜率得到 RT60, 对比早期/后期能量估算干湿比。

    用法:
        estimator = ReverbEstimator(settings)
        reverb = estimator.estimate(dry_audio, wet_audio, sr)
    """

    def __init__(self, settings: EffectsSettings | None = None):
        """初始化混响估算器.

        Args:
            settings: 效果器设置 (可选)
        """
        self.settings = settings or EffectsSettings()
        self.frame_length: int = 2048
        self.hop_length: int = 512
        self.early_window_ms: float = 20.0    # 早期反射窗口
        self.tail_start_ms: float = 80.0       # 混响尾开始时间

    def estimate(
        self,
        dry_audio: np.ndarray,
        wet_audio: np.ndarray,
        sr: int = 44100,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> ReverbEstimate:
        """估算混响参数 / Estimate reverb parameters.

        Args:
            dry_audio: 干音参考音频 (1D)
            wet_audio: 湿音 stem 音频 (1D)
            sr: 采样率
            progress_callback: 进度回调

        Returns:
            ReverbEstimate 包含 rt60_sec 和 dry_wet_ratio
        """
        self._report(progress_callback, 0, "对齐干湿音频…")

        # 对齐长度
        min_len = min(len(dry_audio), len(wet_audio))
        dry = dry_audio[:min_len]
        wet = wet_audio[:min_len]

        self._report(progress_callback, 25, "计算 RMS 包络…")

        # 1. 计算 RMS 包络
        dry_env, times = self._compute_rms_envelope(dry, sr)
        wet_env, _ = self._compute_rms_envelope(wet, sr)

        self._report(progress_callback, 50, "估算 RT60 衰减时间…")

        # 2. 估算 RT60
        rt60 = self._estimate_rt60(dry_env, wet_env, times, sr)

        # 裁剪到合理范围
        rt60 = float(np.clip(
            rt60,
            self.settings.reverb_rt60_min,
            self.settings.reverb_rt60_max,
        ))

        self._report(progress_callback, 75, "估算干湿比…")

        # 3. 估算干湿比
        dry_wet = self._estimate_dry_wet(dry_env, wet_env, times, sr)

        self._report(progress_callback, 100, f"混响估算完成: RT60={rt60:.3f}s")

        return ReverbEstimate(rt60_sec=rt60, dry_wet_ratio=dry_wet)

    # ===== 内部方法 =====

    def _compute_rms_envelope(
        self, audio: np.ndarray, sr: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """计算 RMS 能量包络 / Compute RMS energy envelope.

        Args:
            audio: 音频数据
            sr: 采样率

        Returns:
            (rms_envelope, time_axis_seconds)
        """
        n_frames = (len(audio) - self.frame_length) // self.hop_length + 1
        if n_frames < 1:
            return np.array([np.sqrt(np.mean(audio**2) + 1e-12)]), np.array([0.0])

        env = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * self.hop_length
            frame = audio[start:start + self.frame_length]
            env[i] = np.sqrt(np.mean(frame**2) + 1e-12)

        times = np.arange(n_frames) * self.hop_length / sr
        return env, times

    def _estimate_rt60(
        self,
        dry_env: np.ndarray,
        wet_env: np.ndarray,
        times: np.ndarray,
        sr: int,
    ) -> float:
        """估算 RT60 混响时间 / Estimate RT60 from energy decay curve.

        使用 Schroeder 反向积分法:
          EDC(t) = integral_{t}^{T} h^2(tau) dtau

        在没有纯 IR 的情况下, 使用 wet 包络的衰减尾部近似。

        Args:
            dry_env: 干音 RMS 包络
            wet_env: 湿音 RMS 包络
            times: 时间轴 (秒)
            sr: 采样率

        Returns:
            RT60 (秒)
        """
        # 找到干音结束的时间点 (电平降至峰值 -40dB 以下)
        dry_peak = np.max(dry_env)
        if dry_peak < 1e-10:
            return 0.0

        dry_db = 20.0 * np.log10(dry_env / dry_peak + 1e-12)
        tail_start_indices = np.where(dry_db < -40.0)[0]

        if len(tail_start_indices) == 0:
            # 干音全程在线, 无法分离混响尾
            # 使用 wet 的整体衰减曲线
            return self._estimate_rt60_from_envelope(wet_env, times)

        tail_start = tail_start_indices[0]

        # 从 tail_start 到结尾, wet 的衰减主要是混响
        if tail_start >= len(wet_env) - 10:
            return 0.0  # 尾部太短

        wet_tail = wet_env[tail_start:]

        # Schroeder 反向积分
        edc = np.flip(np.cumsum(np.flip(wet_tail**2)))
        edc_db = 10.0 * np.log10(edc / (edc[0] + 1e-12) + 1e-12)

        # 取 -5dB 到 -25dB 区间做线性拟合 (最可靠的区间)
        fit_start = np.argmax(edc_db < -5.0) if np.any(edc_db < -5.0) else 0
        fit_end = np.argmax(edc_db < -25.0) if np.any(edc_db < -25.0) else len(edc_db) - 1

        if fit_end - fit_start < 3:
            return 0.0

        t_fit = np.arange(fit_start, fit_end) * self.hop_length / sr
        db_fit = edc_db[fit_start:fit_end]

        # 线性拟合: dB = slope * t + intercept
        if len(t_fit) < 2:
            return 0.0

        slope = np.polyfit(t_fit, db_fit, 1)[0]  # dB/s

        if slope >= 0:
            return 0.0  # 无衰减

        # RT60 = -60 / slope
        rt60 = -60.0 / slope
        return rt60

    def _estimate_rt60_from_envelope(
        self, envelope: np.ndarray, times: np.ndarray
    ) -> float:
        """从包络直接估算 RT60 (fallback 方法) / Estimate RT60 from envelope directly.

        Args:
            envelope: RMS 包络
            times: 时间轴

        Returns:
            RT60 (秒)
        """
        # 找到峰值, 从峰值后分析衰减
        peak_idx = int(np.argmax(envelope))
        if peak_idx >= len(envelope) - 10:
            return 0.0

        tail = envelope[peak_idx:]
        edc = np.flip(np.cumsum(np.flip(tail**2)))
        edc_db = 10.0 * np.log10(edc / (edc[0] + 1e-12) + 1e-12)

        # 找到 -5 到 -25 dB 区间
        mask = (edc_db > -30.0) & (edc_db < -3.0)
        if np.sum(mask) < 5:
            return 0.0

        t_fit = np.arange(len(tail))[mask] * self.hop_length / 44100
        db_fit = edc_db[mask]

        slope = np.polyfit(t_fit, db_fit, 1)[0]
        if slope >= 0:
            return 0.0

        return float(-60.0 / slope)

    def _estimate_dry_wet(
        self,
        dry_env: np.ndarray,
        wet_env: np.ndarray,
        times: np.ndarray,
        sr: int,
    ) -> float:
        """估算干湿比 / Estimate dry/wet ratio.

        通过比较早期能量和后期能量来估算。

        Args:
            dry_env: 干音 RMS 包络
            wet_env: 湿音 RMS 包络
            times: 时间轴
            sr: 采样率

        Returns:
            dry_wet_ratio (0=全干, 1=全湿)
        """
        early_samples = int(self.early_window_ms * sr / 1000 / self.hop_length)
        tail_start_samples = int(self.tail_start_ms * sr / 1000 / self.hop_length)

        # 只分析有音频的区域
        dry_peak = np.max(dry_env)
        if dry_peak < 1e-10:
            return 0.0

        # 找到干音峰值后的区域
        peak_idx = int(np.argmax(dry_env))

        # 早期能量: 峰值后 0-20ms
        early_end = min(peak_idx + early_samples, len(wet_env))
        early_energy = float(np.sum(dry_env[peak_idx:early_end]**2))

        # 后期能量: 峰值后 80ms+ 的 wet 能量 (混响尾)
        tail_start = min(peak_idx + tail_start_samples, len(wet_env))
        late_energy = float(np.sum(wet_env[tail_start:]**2))

        # 干湿比估算
        total_energy = early_energy + late_energy
        if total_energy < 1e-12:
            return 0.0

        dry_wet = late_energy / total_energy
        return float(np.clip(dry_wet, 0.0, 1.0))

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
