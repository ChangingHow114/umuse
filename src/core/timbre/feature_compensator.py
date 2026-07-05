"""特征补偿器 / Feature Compensator.

根据估算的效果器参数, 修正 59 维查询特征向量,
消除效果器对音色特征的污染, 提升匹配精度。

核心思路: 已知 EQ/混响/压缩参数 → 估算它们对每个特征维度的贡献 → 从查询向量中减去。
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from src.config.constants import FEATURE_VECTOR_DIM, N_MFCC
from src.core.effects.types import EffectsProfile

logger = logging.getLogger(__name__)


class FeatureCompensator:
    """特征补偿器 / Feature compensator.

    分析效果器对 59 维音色特征向量的影响,
    计算补偿向量以恢复"干音特征"。

    用法:
        compensator = FeatureCompensator()
        f_compensated = compensator.compensate(wet_features, effects_profile)
    """

    def __init__(self, feature_dim: int = FEATURE_VECTOR_DIM):
        """初始化补偿器.

        Args:
            feature_dim: 特征向量维度 (默认 59)
        """
        self.feature_dim = feature_dim
        self.n_mfcc = N_MFCC  # 20

        # 系数: 可调的超参数
        # (经测试, 以下默认值在多数场景下表现良好)
        self.eq_coef: float = 0.15       # EQ 补偿全局强度
        self.reverb_coef: float = 0.10   # 混响补偿全局强度
        self.comp_coef: float = 0.08     # 压缩补偿全局强度

    # ===== 主接口 =====

    def compensate(
        self,
        query_features: np.ndarray,
        effects: EffectsProfile,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> np.ndarray:
        """计算补偿后的特征向量 / Compute compensated feature vector.

        Args:
            query_features: 原始湿音特征向量 (feature_dim,)
            effects: 效果器分析结果
            progress_callback: 进度回调

        Returns:
            补偿后的特征向量 (feature_dim,)
        """
        query = np.asarray(query_features, dtype=np.float64).copy()
        original_norm = np.linalg.norm(query) + 1e-10

        self._report(progress_callback, 10, "计算 EQ 补偿…")
        if effects.eq:
            eq_delta = self._eq_compensation(effects.eq)
            query += eq_delta * self.eq_coef

        self._report(progress_callback, 40, "计算混响补偿…")
        if effects.reverb:
            reverb_delta = self._reverb_compensation(effects.reverb)
            query += reverb_delta * self.reverb_coef

        self._report(progress_callback, 70, "计算压缩补偿…")
        if effects.compression:
            comp_delta = self._compression_compensation(effects.compression)
            query += comp_delta * self.comp_coef

        # 保持特征向量的整体尺度
        new_norm = np.linalg.norm(query) + 1e-10
        query = query * (original_norm / new_norm)

        # Clip 到合理范围
        query = np.clip(query, 0.0, 3.0)

        self._report(progress_callback, 100, "特征补偿完成")
        return query.astype(np.float32)

    # ===== EQ 补偿 =====

    def _eq_compensation(self, eq) -> np.ndarray:  # EQEstimate
        """计算 EQ 补偿向量 / Compute EQ compensation delta.

        EQ 对特征的影响:
          - 高频 boost → MFCC 高频 bins ↑, spectral centroid ↑, rolloff ↑
          - 低频 boost → MFCC 低频 bins ↑
          - 补偿时: 增益为正的方向减去, 增益为负的方向加上

        Args:
            eq: EQEstimate

        Returns:
            59 维补偿向量
        """
        delta = np.zeros(self.feature_dim, dtype=np.float64)

        if not eq or not eq.bands:
            return delta

        for band in eq.bands:
            gain = band.gain_db
            freq = band.center_freq_hz
            q = band.q

            # 补偿方向: 减去 EQ 的效果
            # 即: 如果 EQ boost 了高频, 我们应该降低对应的 MFCC
            correction_sign = -1.0
            correction_magnitude = abs(gain) / 12.0  # 归一化 (假设 max ±12dB)
            width_factor = 1.0 / max(q, 0.5)  # Q 越大(带宽越窄), 影响范围越小

            correction = correction_sign * correction_magnitude * width_factor

            # --- MFCC mean (0-19): 按频率映射到 mel band ---
            mel_band = self._freq_to_mel_band(freq)
            for i in range(self.n_mfcc):
                # 高斯权重: 离目标 mel band 越近, 影响越大
                distance = abs(i - mel_band)
                weight = np.exp(-distance**2 / (2.0 * (2.0 + q)**2))
                delta[i] += correction * weight * 0.5

            # --- Spectral centroid (40): 高频 boost → centroid ↑ ---
            if freq > 2000:
                delta[40] += correction * (freq - 2000) / 8000 * 0.5
            elif freq < 500:
                delta[40] += correction * (freq - 500) / 500 * 0.3

            # --- Spectral bandwidth (41) ---
            delta[41] += correction * 0.2 * width_factor

            # --- Spectral rolloff (42): 类似 centroid ---
            delta[42] += correction * (freq / 10000) * 0.4

            # --- Spectral contrast (43-49, 7 bands): 按频率映射 ---
            contrast_band = self._freq_to_contrast_band(freq)
            for j in range(7):
                dist = abs(j - contrast_band)
                w = np.exp(-dist**2 / 2.0)
                delta[43 + j] += correction * w * 0.3

            # --- Zero-crossing rate (50): 高频 → ZCR ↑ ---
            if freq > 4000:
                delta[50] += correction * 0.3

            # --- Chroma (53-58): 频率通过泛音列影响 chroma ---
            # 简单映射: freq → 最近的 note class
            midi = 69 + 12 * np.log2(freq / 440.0)
            chroma_idx = int(round(midi) % 12) // 2  # 12 → 6
            if 0 <= chroma_idx < 6:
                delta[53 + chroma_idx] += correction * 0.1

        return delta

    def _reverb_compensation(self, reverb) -> np.ndarray:  # ReverbEstimate
        """计算混响补偿向量 / Compute reverb compensation delta.

        混响对特征的影响:
          - 频谱更平稳 → MFCC std ↓ (reverb 让频谱帧间变化减少)
          - 谱对比度降低 → spectral contrast ↓
          - 能量增加 → RMS mean ↑
          - 补偿: 加回被 reverb 消除的变化量

        Args:
            reverb: ReverbEstimate

        Returns:
            59 维补偿向量
        """
        delta = np.zeros(self.feature_dim, dtype=np.float64)

        if not reverb or reverb.rt60_sec < 0.05:
            return delta

        # 归一化参数
        rt60_norm = np.clip(reverb.rt60_sec / 2.0, 0.0, 1.0)  # RT60=2s → 1.0
        strength = reverb.dry_wet_ratio * rt60_norm

        # --- MFCC std (20-39): reverb 让频谱变平稳, std 减小 ---
        # 补偿: 加回 std
        for i in range(20, 40):
            delta[i] += strength * 0.08

        # --- Spectral contrast (43-49): reverb 降低对比度 ---
        # 补偿: 加回对比度
        for i in range(7):
            delta[43 + i] += strength * 0.10

        # --- RMS std (52): reverb 增加变化 → 补偿时减小 ---
        delta[52] -= strength * 0.05

        # --- RMS mean (51): reverb 增加能量 → 补偿时减小 ---
        delta[51] -= strength * 0.05

        # --- Spectral bandwidth (41): reverb 可能增加带宽 ---
        delta[41] -= strength * 0.03

        return delta

    def _compression_compensation(self, comp) -> np.ndarray:  # CompressionEstimate
        """计算压缩补偿向量 / Compute compression compensation delta.

        压缩对特征的影响:
          - 动态范围降低 → RMS std ↓
          - 平均电平提高 (makeup gain) → RMS mean ↑
          - 频谱更均匀 → MFCC std ↓
          - 补偿: 加回被压缩消除的动态范围

        Args:
            comp: CompressionEstimate

        Returns:
            59 维补偿向量
        """
        delta = np.zeros(self.feature_dim, dtype=np.float64)

        if not comp or comp.ratio < 1.2:
            return delta

        # 归一化强度: ratio=4, threshold=-20 → strength=1.0
        strength = (1.0 - 1.0 / comp.ratio) * np.clip(1.0 + comp.threshold_db / 60.0, 0.1, 1.0)

        # --- RMS std (52): 压缩减小标准差 ---
        # 补偿: 加回标准差
        delta[52] += strength * 0.15

        # --- RMS mean (51): makeup gain 提高平均电平 ---
        # 补偿: 减去 makeup gain 的影响
        delta[51] -= comp.makeup_gain_db / 20.0 * 0.3

        # --- MFCC std (20-39): 压缩让频谱更稳定 ---
        # 补偿: 加回变化量
        for i in range(20, 40):
            delta[i] += strength * 0.04

        # --- Spectral contrast (43-49): 轻微影响 ---
        delta[43] -= strength * 0.05
        delta[49] -= strength * 0.05

        return delta

    # ===== 辅助映射 =====

    @staticmethod
    def _freq_to_mel_band(freq_hz: float) -> int:
        """将频率映射到 20 个 mel band / Map frequency to mel band index (0-19).

        Args:
            freq_hz: 频率 (Hz)

        Returns:
            mel band 索引 (0-19)
        """
        # 简化: 使用对数映射
        if freq_hz <= 0:
            return 0
        # mel 刻度: 20Hz → 0, 20000Hz → 19
        min_log = np.log(20.0)
        max_log = np.log(20000.0)
        log_freq = np.log(max(freq_hz, 20.0))
        band = int((log_freq - min_log) / (max_log - min_log) * 19)
        return max(0, min(19, band))

    @staticmethod
    def _freq_to_contrast_band(freq_hz: float) -> int:
        """将频率映射到 7 个 spectral contrast band / Map frequency to contrast band (0-6).

        librosa 的 spectral contrast 将频谱分为 7 个 octave-based 频段:
          0: 0-200Hz, 1: 200-400, 2: 400-800, 3: 800-1600,
          4: 1600-3200, 5: 3200-6400, 6: 6400-20000

        Args:
            freq_hz: 频率 (Hz)

        Returns:
            contrast band 索引 (0-6)
        """
        if freq_hz < 200:
            return 0
        elif freq_hz < 400:
            return 1
        elif freq_hz < 800:
            return 2
        elif freq_hz < 1600:
            return 3
        elif freq_hz < 3200:
            return 4
        elif freq_hz < 6400:
            return 5
        else:
            return 6

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
