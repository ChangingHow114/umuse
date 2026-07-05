"""音色特征提取器 / Timbre Feature Extractor.

从音频中提取用于音色匹配的多维特征向量。
Extracts multi-dimensional feature vectors from audio for timbre matching.

特征维度 (59-dim, 对齐 constants.FEATURE_VECTOR_DIM):
  - MFCC mean (20): 梅尔倒谱系数均值
  - MFCC std  (20): 梅尔倒谱系数标准差
  - Spectral Centroid (1): 频谱质心
  - Spectral Bandwidth (1): 频谱带宽
  - Spectral Rolloff (1): 频谱滚降点
  - Spectral Contrast (7): 频谱对比度 (7 个频段)
  - Zero-Crossing Rate (1): 过零率
  - RMS Energy mean (1): 均方根能量均值
  - RMS Energy std  (1): 均方根能量标准差
  - Chroma mean (6): 半音特征 (12→6 降维)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np
import librosa

from src.config.constants import (
    DEFAULT_SAMPLE_RATE,
    DEFAULT_N_FFT,
    DEFAULT_HOP_LENGTH,
    N_MFCC,
    FEATURE_VECTOR_DIM,
)

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """音色特征提取器 / Timbre feature extractor.

    用法:
        extractor = FeatureExtractor()
        features = extractor.extract("piano_stem.wav")
        # features.shape == (59,)
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        n_fft: int = DEFAULT_N_FFT,
        hop_length: int = DEFAULT_HOP_LENGTH,
        n_mfcc: int = N_MFCC,
        feature_dim: int = FEATURE_VECTOR_DIM,
    ):
        """初始化特征提取器.

        Args:
            sample_rate: 目标采样率 (Hz)
            n_fft: FFT 窗口大小
            hop_length: 帧移 (samples)
            n_mfcc: MFCC 系数个数
            feature_dim: 目标特征向量维度 (用于校验)
        """
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mfcc = n_mfcc
        self.feature_dim = feature_dim

    # ===== 主接口 =====

    def extract(
        self,
        audio_path: Path | str,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> np.ndarray:
        """从音频文件提取特征向量 / Extract feature vector from audio file.

        Args:
            audio_path: 音频文件路径
            progress_callback: 进度回调 (percent, message)

        Returns:
            特征向量 (feature_dim,)
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        self._report(progress_callback, 5, "加载音频…")
        y, sr = librosa.load(str(audio_path), sr=self.sample_rate, mono=True)

        # 跳过静音
        if np.max(np.abs(y)) < 0.001:
            logger.warning("音频接近静音, 返回零向量")
            return np.zeros(self.feature_dim, dtype=np.float32)

        self._report(progress_callback, 15, "提取频谱…")
        S = np.abs(librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length))

        self._report(progress_callback, 25, "提取 MFCC…")
        mfcc = librosa.feature.mfcc(
            y=y, sr=sr, n_mfcc=self.n_mfcc,
            n_fft=self.n_fft, hop_length=self.hop_length,
        )

        self._report(progress_callback, 40, "提取频谱特征…")
        centroid = librosa.feature.spectral_centroid(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length,
        )
        bandwidth = librosa.feature.spectral_bandwidth(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length,
        )
        rolloff = librosa.feature.spectral_rolloff(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length,
        )
        contrast = librosa.feature.spectral_contrast(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length,
        )

        self._report(progress_callback, 55, "提取时序特征…")
        zcr = librosa.feature.zero_crossing_rate(
            y, frame_length=self.n_fft, hop_length=self.hop_length,
        )
        rms = librosa.feature.rms(
            y=y, frame_length=self.n_fft, hop_length=self.hop_length,
        )

        self._report(progress_callback, 70, "提取半音特征…")
        chroma = librosa.feature.chroma_stft(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length,
        )

        self._report(progress_callback, 85, "组装特征向量…")
        feature_vec = self._assemble_feature_vector(
            mfcc, centroid, bandwidth, rolloff, contrast, zcr, rms, chroma,
        )

        self._report(progress_callback, 100, "特征提取完成")
        return feature_vec.astype(np.float32)

    def extract_from_array(
        self,
        y: np.ndarray,
        sr: int | None = None,
    ) -> np.ndarray:
        """从音频数组提取特征 (无需文件 I/O).

        Args:
            y: 音频样本数组 (mono)
            sr: 采样率 (默认使用 self.sample_rate)

        Returns:
            特征向量 (feature_dim,)
        """
        if sr is None:
            sr = self.sample_rate
        if sr != self.sample_rate:
            y = librosa.resample(y, orig_sr=sr, target_sr=self.sample_rate)
            sr = self.sample_rate

        S = np.abs(librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length))
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=self.n_mfcc, n_fft=self.n_fft, hop_length=self.hop_length)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length)
        bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length)
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length)
        zcr = librosa.feature.zero_crossing_rate(y, frame_length=self.n_fft, hop_length=self.hop_length)
        rms = librosa.feature.rms(y=y, frame_length=self.n_fft, hop_length=self.hop_length)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length)

        return self._assemble_feature_vector(
            mfcc, centroid, bandwidth, rolloff, contrast, zcr, rms, chroma,
        ).astype(np.float32)

    # ===== 内部方法 =====

    def _assemble_feature_vector(
        self,
        mfcc: np.ndarray,
        centroid: np.ndarray,
        bandwidth: np.ndarray,
        rolloff: np.ndarray,
        contrast: np.ndarray,
        zcr: np.ndarray,
        rms: np.ndarray,
        chroma: np.ndarray,
    ) -> np.ndarray:
        """组装最终特征向量 / Assemble final feature vector.

        将所有统计量拼接为固定维度特征向量。
        各特征取时间轴均值 (必要时也取标准差), 拼接后对齐到 FEATURE_VECTOR_DIM。
        """
        parts: list[np.ndarray] = []

        # 1. MFCC mean + std (N_MFCC * 2 = 40)
        parts.append(np.mean(mfcc, axis=1))     # (20,)
        parts.append(np.std(mfcc, axis=1))      # (20,)

        # 2. Spectral centroid mean (1)
        parts.append(np.array([np.mean(centroid)]))

        # 3. Spectral bandwidth mean (1)
        parts.append(np.array([np.mean(bandwidth)]))

        # 4. Spectral rolloff mean (1)
        parts.append(np.array([np.mean(rolloff)]))

        # 5. Spectral contrast mean (7)
        # contrast shape: (7 bands + 1 valley, frames) → take first 7 bands
        if contrast.shape[0] >= 7:
            parts.append(np.mean(contrast[:7, :], axis=1))
        else:
            parts.append(np.mean(contrast, axis=1))

        # 6. Zero-crossing rate mean (1)
        parts.append(np.array([np.mean(zcr)]))

        # 7. RMS energy mean + std (2)
        parts.append(np.array([np.mean(rms)]))
        parts.append(np.array([np.std(rms)]))

        # 8. Chroma mean → reduced to 6
        # chroma shape: (12, frames), average pairs to get 6
        chroma_mean = np.mean(chroma, axis=1)  # (12,)
        # 相邻半音对取均值: (C+C#)/2, (D+D#)/2, ..., (A#+B)/2
        chroma_reduced = np.array([
            (chroma_mean[0] + chroma_mean[1]) / 2,   # C/C#
            (chroma_mean[2] + chroma_mean[3]) / 2,   # D/D#
            (chroma_mean[4] + chroma_mean[5]) / 2,   # E/F
            (chroma_mean[6] + chroma_mean[7]) / 2,   # F#/G
            (chroma_mean[8] + chroma_mean[9]) / 2,   # G#/A
            (chroma_mean[10] + chroma_mean[11]) / 2, # A#/B
        ])
        parts.append(chroma_reduced)  # (6,)

        # 拼接并校验维度
        vec = np.concatenate(parts)
        expected = 20 + 20 + 1 + 1 + 1 + 7 + 1 + 1 + 1 + 6  # = 59

        if len(vec) > self.feature_dim:
            vec = vec[:self.feature_dim]
        elif len(vec) < self.feature_dim:
            padding = np.zeros(self.feature_dim - len(vec))
            vec = np.concatenate([vec, padding])

        return vec

    @staticmethod
    def _report(
        callback: Callable[[int, str], None] | None,
        pct: int,
        msg: str,
    ) -> None:
        """安全的进度回调."""
        if callback:
            try:
                callback(pct, msg)
            except Exception:
                logging.getLogger(__name__).debug(
                    "特征提取进度回调异常 (忽略)", exc_info=True,
                )


def compare_features(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个特征向量的余弦相似度 / Compute cosine similarity.

    Args:
        a, b: 特征向量

    Returns:
        余弦相似度 (0-1, 越高越相似)
    """
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compare_features_euclidean(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个特征向量的欧几里得距离 / Compute Euclidean distance.

    Returns:
        归一化距离 (0-1, 越低越相似)
    """
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    dist = np.linalg.norm(a - b)
    # 归一化: 使用特征向量维度作为最大可能距离的近似
    return float(dist / np.sqrt(len(a)))
