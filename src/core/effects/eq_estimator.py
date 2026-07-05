"""EQ 参数估算器 / EQ Parameter Estimator.

通过对比干音和湿音的频谱包络差分, 拟合参数化 EQ 频段。
算法: 频谱差分 + 峰值检测 + 参数化曲线拟合
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np
from scipy.signal import savgol_filter, find_peaks, peak_widths
from scipy.optimize import minimize

from src.config.constants import EQ_MAX_BANDS, EQ_FREQ_RANGE
from src.config.settings import EffectsSettings
from src.core.effects.types import EQBand, EQEstimate

logger = logging.getLogger(__name__)


class EQEstimator:
    """EQ 参数估算器 / EQ parameter estimator.

    对比干音参考和湿音 stem 的频谱, 推断应用的 EQ 参数。
    输出最多 EQ_MAX_BANDS 个参数化频段。

    用法:
        estimator = EQEstimator(settings)
        eq = estimator.estimate(dry_audio, wet_audio, sr)
    """

    def __init__(self, settings: EffectsSettings | None = None):
        """初始化 EQ 估算器.

        Args:
            settings: 效果器设置 (可选, 使用默认值)
        """
        self.settings = settings or EffectsSettings()
        self.n_fft: int = 2048
        self.hop_length: int = 512

    def estimate(
        self,
        dry_audio: np.ndarray,
        wet_audio: np.ndarray,
        sr: int = 44100,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> EQEstimate:
        """估算 EQ 参数 / Estimate EQ parameters.

        Args:
            dry_audio: 干音参考音频 (1D)
            wet_audio: 湿音 stem 音频 (1D)
            sr: 采样率
            progress_callback: 进度回调

        Returns:
            EQEstimate 包含频段列表
        """
        self._report(progress_callback, 0, "计算干/湿音频谱…")

        # 1. 对齐长度: 取较短的
        min_len = min(len(dry_audio), len(wet_audio))
        dry = dry_audio[:min_len]
        wet = wet_audio[:min_len]

        # 2. 计算平均幅度谱
        dry_spec, freqs = self._compute_avg_spectrum(dry, sr)
        wet_spec, _ = self._compute_avg_spectrum(wet, sr)

        self._report(progress_callback, 30, "计算频谱差分…")

        # 3. 计算 dB 差分
        eps = 1e-8
        diff_db = 20.0 * np.log10((wet_spec + eps) / (dry_spec + eps))

        # 4. Savitzky-Golay 平滑
        window = self.settings.eq_smooth_window
        if window % 2 == 0:
            window += 1  # 必须是奇数
        if window < 5:
            window = 5
        diff_smooth = savgol_filter(diff_db, window_length=window, polyorder=2)

        self._report(progress_callback, 50, "检测 EQ 峰值…")

        # 5. 检测峰值和谷值
        bands = self._detect_eq_peaks(diff_smooth, freqs, min_gain_db=2.0)

        self._report(progress_callback, 70, "拟合参数化 EQ…")

        # 6. 精修每个频段的参数
        bands = self._refine_bands(diff_smooth, freqs, bands)

        # 7. 预估宽带增益 (差分均值)
        pre_gain = float(np.mean(diff_smooth))

        self._report(progress_callback, 100, f"EQ 估算完成: {len(bands)} 个频段")

        return EQEstimate(bands=bands, pre_gain_db=round(pre_gain, 2))

    # ===== 内部方法 =====

    def _compute_avg_spectrum(
        self, audio: np.ndarray, sr: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """计算长时平均幅度谱 / Compute long-term average magnitude spectrum.

        Args:
            audio: 音频数据
            sr: 采样率

        Returns:
            (avg_magnitude, frequency_bins)
        """
        # Welch 方法: 分段 STFT, 取平均功率
        from scipy.signal import welch

        freqs, psd = welch(
            audio, fs=sr, nperseg=self.n_fft,
            noverlap=self.n_fft // 2, scaling="spectrum",
        )

        # PSD → 幅度
        magnitude = np.sqrt(psd + 1e-12)

        # 只保留 EQ_FREQ_RANGE 范围内的频率
        mask = (freqs >= EQ_FREQ_RANGE[0]) & (freqs <= EQ_FREQ_RANGE[1])
        return magnitude[mask].astype(np.float64), freqs[mask].astype(np.float64)

    def _detect_eq_peaks(
        self,
        diff_db: np.ndarray,
        freqs: np.ndarray,
        min_gain_db: float = 2.0,
    ) -> list[EQBand]:
        """在差分曲线上检测 EQ 峰值/谷值 / Detect EQ peaks and dips.

        Args:
            diff_db: 平滑后的 dB 差分曲线
            freqs: 频率轴
            min_gain_db: 最小增益阈值 (低于此值的峰谷忽略)

        Returns:
            检测到的 EQBand 列表 (未精修)
        """
        # 检测正峰 (boost)
        peaks, peak_props = find_peaks(diff_db, height=min_gain_db, distance=10)
        # 检测负谷 (cut)
        dips, dip_props = find_peaks(-diff_db, height=min_gain_db, distance=10)

        bands: list[EQBand] = []

        for idx in peaks:
            gain = float(diff_db[idx])
            # 通过峰值宽度估算 Q 值
            widths = peak_widths(diff_db, [idx], rel_height=0.5)[0]
            bw_hz = float(widths[0]) * (freqs[1] - freqs[0]) if len(widths) > 0 else freq_at_idx / 2.0
            freq_at_idx = float(freqs[idx])
            q = freq_at_idx / max(bw_hz, 1.0)
            q = np.clip(q, 0.3, 10.0)

            # 判断滤波器类型
            filter_type = self._classify_band(freq_at_idx, gain)

            bands.append(EQBand(
                center_freq_hz=freq_at_idx,
                gain_db=gain,
                q=float(q),
                filter_type=filter_type,
            ))

        for idx in dips:
            gain = float(diff_db[idx])   # 负值
            widths = peak_widths(-diff_db, [idx], rel_height=0.5)[0]
            bw_hz = float(widths[0]) * (freqs[1] - freqs[0]) if len(widths) > 0 else freq_at_idx / 2.0
            freq_at_idx = float(freqs[idx])
            q = freq_at_idx / max(bw_hz, 1.0)
            q = np.clip(q, 0.3, 10.0)

            filter_type = self._classify_band(freq_at_idx, gain)

            bands.append(EQBand(
                center_freq_hz=freq_at_idx,
                gain_db=gain,
                q=float(q),
                filter_type=filter_type,
            ))

        # 按 |gain| 降序排列, 只保留最强的前 N 个
        bands.sort(key=lambda b: abs(b.gain_db), reverse=True)
        return bands[:EQ_MAX_BANDS]

    def _classify_band(self, freq_hz: float, gain_db: float) -> str:
        """判断 EQ 频段的滤波器类型 / Classify filter type based on frequency.

        Args:
            freq_hz: 中心频率
            gain_db: 增益

        Returns:
            滤波器类型字符串
        """
        if freq_hz < 100:
            return "low_shelf"
        elif freq_hz > 8000:
            return "high_shelf"
        else:
            return "peak"

    def _refine_bands(
        self,
        diff_db: np.ndarray,
        freqs: np.ndarray,
        bands: list[EQBand],
    ) -> list[EQBand]:
        """用数值优化精修 EQ 频段参数 / Refine band parameters via optimization.

        Args:
            diff_db: 目标 dB 差分曲线
            freqs: 频率轴
            bands: 初始猜测的频段列表

        Returns:
            精修后的 EQBand 列表
        """
        if not bands:
            return bands

        refined: list[EQBand] = []

        for band in bands:
            # 初始猜测
            x0 = [band.center_freq_hz, band.gain_db, band.q]

            def objective(x: np.ndarray) -> float:
                """最小化拟合误差."""
                fc, gain, q_val = x
                fc = np.clip(fc, 20.0, 20000.0)
                q_val = np.clip(q_val, 0.3, 10.0)
                # 参数化 peak/shelf 滤波器的幅频响应 (简化版)
                # H(f) = gain / sqrt(1 + ((f/fc - fc/f)^2 * Q^2))
                # 实际使用标准 peaking EQ 公式
                pred = self._peaking_eq_response(freqs, fc, gain, q_val)
                error = np.sum((pred - diff_db) ** 2)
                return float(error)

            try:
                result = minimize(
                    objective,
                    x0,
                    method="Nelder-Mead",
                    options={"maxiter": 200, "xatol": 0.1},
                )
                if result.success or result.fun < objective(x0):
                    fc, gain, q_val = result.x
                    band.center_freq_hz = np.clip(float(fc), 20.0, 20000.0)
                    band.gain_db = float(gain)
                    band.q = np.clip(float(q_val), 0.3, 10.0)
            except Exception:
                pass  # 优化失败, 保留初始值

            refined.append(band)

        # 合并频率过近的频段
        refined = self._merge_close_bands(refined)

        return refined

    def _peaking_eq_response(
        self,
        freqs: np.ndarray,
        fc: float,
        gain_db: float,
        q: float,
    ) -> np.ndarray:
        """计算 peaking EQ 的频率响应 / Compute peaking EQ frequency response.

        Args:
            freqs: 频率轴
            fc: 中心频率
            gain_db: 增益 (dB)
            q: Q 值

        Returns:
            幅频响应 (dB)
        """
        # RBJ Peaking EQ 公式
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * fc
        alpha = np.sin(w0) / (2.0 * q) if q > 0 else 1.0

        # 简化: 使用带通形状近似
        omega = freqs / fc
        # biquad peaking filter magnitude
        with np.errstate(divide="ignore", invalid="ignore"):
            num = (omega**2 - 1.0)**2 + (omega / q)**2
            den = (omega**2 - 1.0)**2 + (omega * A / q)**2
            response_db = 20.0 * np.log10(np.sqrt(num / (den + 1e-12)) + 1e-12)

        response_db = np.nan_to_num(response_db, nan=0.0, posinf=20.0, neginf=-20.0)
        return response_db + gain_db

    def _merge_close_bands(self, bands: list[EQBand]) -> list[EQBand]:
        """合并频率过近的频段 / Merge bands that are too close in frequency.

        Args:
            bands: EQ 频段列表

        Returns:
            合并后的列表
        """
        if len(bands) <= 1:
            return bands

        # 按频率排序
        sorted_bands = sorted(bands, key=lambda b: b.center_freq_hz)
        merged: list[EQBand] = []

        for band in sorted_bands:
            if not merged:
                merged.append(band)
                continue

            last = merged[-1]
            # 如果频率间隔 < 0.5 octave, 合并
            if band.center_freq_hz / last.center_freq_hz < 1.4:
                # 取加权平均
                w_last = abs(last.gain_db)
                w_band = abs(band.gain_db)
                total_w = w_last + w_band
                if total_w > 0:
                    last.center_freq_hz = (
                        last.center_freq_hz * w_last + band.center_freq_hz * w_band
                    ) / total_w
                    last.gain_db = (last.gain_db * w_last + band.gain_db * w_band) / total_w
                    last.q = max(last.q, band.q)
            else:
                merged.append(band)

        return merged

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
