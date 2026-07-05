"""动态/压缩参数估算器 / Dynamics / Compression Parameter Estimator.

通过对比干湿信号的 RMS 分布和包络动态,
估算压缩器的 threshold / ratio / attack / release 参数。
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from src.config.settings import EffectsSettings
from src.core.effects.types import CompressionEstimate

logger = logging.getLogger(__name__)


class DynamicsEstimator:
    """压缩器参数估算器 / Compression parameter estimator.

    对比干湿信号的 RMS 分布统计和瞬态包络,
    推断压缩器的 threshold、ratio、attack、release。

    用法:
        estimator = DynamicsEstimator(settings)
        comp = estimator.estimate(dry_audio, wet_audio, sr)
    """

    def __init__(self, settings: EffectsSettings | None = None):
        """初始化压缩估算器.

        Args:
            settings: 效果器设置 (可选)
        """
        self.settings = settings or EffectsSettings()
        self.frame_length: int = 1024
        self.hop_length: int = 256
        self.min_transient_db: float = -30.0  # 瞬态检测阈值

    def estimate(
        self,
        dry_audio: np.ndarray,
        wet_audio: np.ndarray,
        sr: int = 44100,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> CompressionEstimate:
        """估算压缩参数 / Estimate compression parameters.

        Args:
            dry_audio: 干音参考音频 (1D)
            wet_audio: 湿音 stem 音频 (1D)
            sr: 采样率
            progress_callback: 进度回调

        Returns:
            CompressionEstimate 包含压缩器参数
        """
        self._report(progress_callback, 0, "对齐干湿音频…")

        # 对齐长度
        min_len = min(len(dry_audio), len(wet_audio))
        dry = dry_audio[:min_len]
        wet = wet_audio[:min_len]

        self._report(progress_callback, 20, "计算 RMS 分布 (dB)…")

        # 1. 计算帧级 RMS (dB)
        dry_rms_db = self._compute_rms_db(dry, sr)
        wet_rms_db = self._compute_rms_db(wet, sr)

        self._report(progress_callback, 40, "估算 threshold 和 ratio…")

        # 2. 估算 threshold 和 ratio
        threshold_db, ratio = self._estimate_threshold_ratio(
            dry_rms_db, wet_rms_db
        )

        self._report(progress_callback, 60, "检测瞬态…")

        # 3. 估算 attack 和 release
        attack_ms, release_ms = self._estimate_attack_release(
            dry, wet, sr
        )

        # 4. 估算 makeup gain
        makeup_gain = self._estimate_makeup_gain(dry_rms_db, wet_rms_db)

        self._report(progress_callback, 100, "压缩估算完成")

        return CompressionEstimate(
            threshold_db=round(threshold_db, 1),
            ratio=round(ratio, 2),
            attack_ms=round(attack_ms, 1),
            release_ms=round(release_ms, 1),
            makeup_gain_db=round(makeup_gain, 2),
        )

    # ===== 内部方法 =====

    def _compute_rms_db(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """计算帧级 RMS (dB) / Compute frame-wise RMS in dB.

        Args:
            audio: 音频数据
            sr: 采样率

        Returns:
            RMS dB 值数组
        """
        n_frames = (len(audio) - self.frame_length) // self.hop_length + 1
        if n_frames < 1:
            return np.array([0.0])

        rms = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * self.hop_length
            frame = audio[start:start + self.frame_length]
            rms[i] = np.sqrt(np.mean(frame**2) + 1e-12)

        # 转为 dB (相对于峰值)
        peak = np.max(rms) if np.max(rms) > 1e-10 else 1.0
        rms_db = 20.0 * np.log10(rms / peak + 1e-12)

        return rms_db

    def _estimate_threshold_ratio(
        self,
        dry_rms_db: np.ndarray,
        wet_rms_db: np.ndarray,
    ) -> tuple[float, float]:
        """估算 threshold 和 ratio / Estimate threshold and ratio.

        通过对比 RMS 的排序分布来推断压缩参数。

        Args:
            dry_rms_db: 干音 RMS (dB)
            wet_rms_db: 湿音 RMS (dB)

        Returns:
            (threshold_db, ratio)
        """
        # 排序 (低到高), 用于分析动态范围
        dry_sorted = np.sort(dry_rms_db)
        wet_sorted = np.sort(wet_rms_db)

        # 确保长度一致
        min_len = min(len(dry_sorted), len(wet_sorted))
        dry_sorted = dry_sorted[-min_len:]  # 取尾部 (高电平部分)
        wet_sorted = wet_sorted[-min_len:]

        # 计算每个百分位的差异
        diff = dry_sorted - wet_sorted

        # 检测差异突变 (knee point)
        # 在 diff 曲线上寻找拐点
        if len(diff) < 10:
            return -20.0, 1.0

        # 平滑 diff
        from scipy.ndimage import uniform_filter1d
        diff_smooth = uniform_filter1d(diff, size=min(11, len(diff) // 3 * 2 + 1))

        # 找 diff 显著增大的位置 (dry 比 wet 高很多)
        # 这是压缩器开始工作的阈值区域
        significant_mask = diff_smooth > 3.0  # 3dB 差异

        if not np.any(significant_mask):
            # 无明显压缩
            return -10.0, 1.0

        # 取 significant 区域的 25th 百分位对应的 dry 电平作为 threshold
        sig_indices = np.where(significant_mask)[0]
        threshold_idx = sig_indices[len(sig_indices) // 4]  # 1/4 处
        threshold_db = float(dry_sorted[threshold_idx])

        # 估算 ratio
        # ratio = Δinput / Δoutput  (在 threshold 以上)
        above_threshold = dry_sorted > threshold_db
        if np.sum(above_threshold) < 5:
            return threshold_db, 1.0

        dry_above = dry_sorted[above_threshold]
        wet_above = wet_sorted[above_threshold]

        # 线性拟合: wet = a * dry + b
        if len(dry_above) >= 2:
            slope = np.polyfit(dry_above, wet_above, 1)[0]
            # slope = 1/ratio (in dB domain)
            if slope > 0.1:
                ratio = 1.0 / slope
            else:
                ratio = 10.0
        else:
            ratio = 1.0

        ratio = float(np.clip(ratio, 1.0, 20.0))
        return threshold_db, ratio

    def _estimate_attack_release(
        self,
        dry_audio: np.ndarray,
        wet_audio: np.ndarray,
        sr: int,
    ) -> tuple[float, float]:
        """估算 attack 和 release 时间 / Estimate attack and release times.

        通过检测瞬态, 对比干湿信号的包络响应速度。

        Args:
            dry_audio: 干音
            wet_audio: 湿音
            sr: 采样率

        Returns:
            (attack_ms, release_ms)
        """
        # 简化的瞬态检测: 寻找 RMS 快速上升的位置
        dry_env, _ = self._compute_envelope_fast(dry_audio, sr)
        wet_env, _ = self._compute_envelope_fast(wet_audio, sr)

        # 检测干音中的瞬态 (RMS 快速上升)
        if len(dry_env) < 10:
            return 10.0, 100.0

        env_diff = np.diff(dry_env)
        env_diff = np.append(env_diff, 0)

        # 正差分 (上升沿)
        threshold = np.percentile(env_diff[env_diff > 0], 70) if np.any(env_diff > 0) else np.max(env_diff) * 0.5
        onsets = np.where(env_diff > threshold)[0]

        if len(onsets) < 3:
            return 10.0, 100.0  # 瞬态不足, 使用默认值

        # 对每个瞬态, 计算干湿信号的响应时间
        attack_times = []
        release_times = []

        for onset in onsets[:10]:  # 最多分析 10 个瞬态
            # Attack: 上升时间 (到达峰值的 63%)
            attack_dry, attack_wet = self._measure_attack(
                dry_env, wet_env, onset, sr
            )
            if attack_dry is not None and attack_wet is not None:
                attack_times.append(attack_wet)
                # attack_wet > attack_dry 说明压缩器增加了 attack 时间

            # Release: 下降时间 (衰减到峰值的 37%)
            release_dry, release_wet = self._measure_release(
                dry_env, wet_env, onset, sr
            )
            if release_dry is not None and release_wet is not None:
                release_times.append(release_wet)

        # 取中位数
        if attack_times:
            attack_ms = np.median(attack_times) * 1000.0
        else:
            attack_ms = 10.0

        if release_times:
            release_ms = np.median(release_times) * 1000.0
        else:
            release_ms = 100.0

        return float(np.clip(attack_ms, 0.5, 200.0)), float(np.clip(release_ms, 5.0, 2000.0))

    def _compute_envelope_fast(
        self, audio: np.ndarray, sr: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """快速计算能量包络 (比 RMS 更粗) / Fast envelope calculation.

        Args:
            audio: 音频数据
            sr: 采样率

        Returns:
            (envelope, time_axis)
        """
        hop = self.hop_length // 2  # 更密的时间分辨率
        n_frames = (len(audio) - self.frame_length) // hop + 1
        if n_frames < 1:
            return np.array([0.0]), np.array([0.0])

        env = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + self.frame_length]
            env[i] = np.sqrt(np.mean(frame**2) + 1e-12)

        times = np.arange(n_frames) * hop / sr
        return env, times

    def _measure_attack(
        self,
        dry_env: np.ndarray,
        wet_env: np.ndarray,
        onset_idx: int,
        sr: int,
    ) -> tuple[float | None, float | None]:
        """测量单次瞬态的 attack 时间 / Measure attack time for one transient.

        Args:
            dry_env: 干音包络
            wet_env: 湿音包络
            onset_idx: 瞬态起始帧索引
            sr: 采样率

        Returns:
            (dry_attack_sec, wet_attack_sec) 或 None
        """
        # 找峰值位置 (onset 后 50ms 内的最大值)
        window = int(0.05 * sr / (self.hop_length // 2))  # 50ms

        if onset_idx >= len(dry_env) - 2 or onset_idx >= len(wet_env) - 2:
            return None, None

        dry_peak_idx = onset_idx + np.argmax(dry_env[onset_idx:min(onset_idx + window, len(dry_env))])
        wet_peak_idx = onset_idx + np.argmax(wet_env[onset_idx:min(onset_idx + window, len(wet_env))])

        # 上升时间: onset → peak 的帧数 * hop / sr
        hop_sec = (self.hop_length // 2) / sr

        dry_attack = (dry_peak_idx - onset_idx) * hop_sec
        wet_attack = (wet_peak_idx - onset_idx) * hop_sec

        return max(dry_attack, 0.001), max(wet_attack, 0.001)

    def _measure_release(
        self,
        dry_env: np.ndarray,
        wet_env: np.ndarray,
        onset_idx: int,
        sr: int,
    ) -> tuple[float | None, float | None]:
        """测量单次瞬态的 release 时间 / Measure release time for one transient.

        Args:
            dry_env: 干音包络
            wet_env: 湿音包络
            onset_idx: 瞬态起始帧索引
            sr: 采样率

        Returns:
            (dry_release_sec, wet_release_sec) 或 None
        """
        hop_sec = (self.hop_length // 2) / sr
        window = int(0.2 * sr / (self.hop_length // 2))  # 200ms

        # 找峰值后的衰减
        if onset_idx >= len(dry_env) - 2 or onset_idx >= len(wet_env) - 2:
            return None, None

        dry_peak_idx = onset_idx + np.argmax(dry_env[onset_idx:min(onset_idx + window // 2, len(dry_env))])
        wet_peak_idx = onset_idx + np.argmax(wet_env[onset_idx:min(onset_idx + window // 2, len(wet_env))])

        # 从峰值衰减到 37% (1/e) 的时间
        dry_peak_val = dry_env[dry_peak_idx]
        wet_peak_val = wet_env[wet_peak_idx]

        dry_target = dry_peak_val * 0.37
        wet_target = wet_peak_val * 0.37

        # 从峰值开始搜索
        dry_release = self._find_decay_time(dry_env, dry_peak_idx, dry_target, hop_sec)
        wet_release = self._find_decay_time(wet_env, wet_peak_idx, wet_target, hop_sec)

        return dry_release, wet_release

    def _find_decay_time(
        self,
        env: np.ndarray,
        peak_idx: int,
        target_val: float,
        hop_sec: float,
    ) -> float | None:
        """找衰减到目标值的时间 / Find decay time to target value.

        Args:
            env: 包络数组
            peak_idx: 峰值索引
            target_val: 目标值
            hop_sec: 每帧的时间 (秒)

        Returns:
            衰减时间 (秒), 或 None
        """
        for j in range(peak_idx + 1, min(peak_idx + 200, len(env))):
            if env[j] <= target_val:
                return (j - peak_idx) * hop_sec
        return None

    def _estimate_makeup_gain(
        self,
        dry_rms_db: np.ndarray,
        wet_rms_db: np.ndarray,
    ) -> float:
        """估算 makeup gain / Estimate makeup gain.

        对比干湿信号的整体电平差异。

        Args:
            dry_rms_db: 干音 RMS (dB)
            wet_rms_db: 湿音 RMS (dB)

        Returns:
            makeup_gain_db
        """
        # 取各自的上四分位数 (忽略静音段)
        dry_median = float(np.percentile(dry_rms_db, 75))
        wet_median = float(np.percentile(wet_rms_db, 75))

        gain = wet_median - dry_median
        return float(np.clip(gain, -12.0, 12.0))

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
