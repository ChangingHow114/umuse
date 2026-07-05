"""音频读写工具 / Audio I/O Utilities.

统一的音频加载/保存接口，支持 WAV/MP3/FLAC/OGG 等格式。
解决不同库之间的采样率、通道数、数据类型差异。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf
import librosa
from pydub import AudioSegment


def load_audio(
    file_path: str | Path,
    target_sr: int = 44100,
    mono: bool = False,
    dtype: str = "float32",
) -> tuple[np.ndarray, int]:
    """加载音频文件为 numpy 数组 / Load audio file as numpy array.

    Args:
        file_path: 输入文件路径 (支持 wav/mp3/flac/ogg/m4a)
        target_sr: 目标采样率 Hz
        mono: 是否强制单声道 (True=取平均声道)
        dtype: 输出数据类型 ('float32' | 'float64' | 'int16')

    Returns:
        (audio_array, sample_rate)
        - audio_array: shape=(n_samples,) 或 (n_channels, n_samples)
        - sample_rate: 实际采样率 (等于 target_sr)

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    suffix = file_path.suffix.lower()

    # MP3/m4a/aac → 使用 pydub 解码 (soundfile 不支持)
    if suffix in (".mp3", ".m4a", ".aac"):
        audio, sr = _load_with_pydub(file_path, target_sr, mono)
    else:
        # WAV/FLAC/OGG → 使用 soundfile (高效)
        audio, sr = _load_with_soundfile(file_path, target_sr, mono)

    # 类型转换
    if dtype == "float32":
        audio = audio.astype(np.float32)
    elif dtype == "float64":
        audio = audio.astype(np.float64)
    elif dtype == "int16":
        audio = (audio * 32767).astype(np.int16)

    return audio, target_sr


def _load_with_soundfile(
    file_path: Path, target_sr: int, mono: bool
) -> tuple[np.ndarray, int]:
    """使用 soundfile 加载音频."""
    # 获取原始采样率
    info = sf.info(file_path)
    orig_sr = info.samplerate

    # 读取音频
    audio, sr = sf.read(file_path, dtype="float32")
    # sf.read returns shape (samples, channels) or (samples,)

    # 转置为 (channels, samples) 以便统一处理
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)  # (1, samples)
    else:
        audio = audio.T  # (channels, samples)

    # 重采样
    if orig_sr != target_sr:
        audio = librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)

    # 单声道
    if mono and audio.shape[0] > 1:
        audio = audio.mean(axis=0, keepdims=True)

    return audio, target_sr


def _load_with_pydub(
    file_path: Path, target_sr: int, mono: bool
) -> tuple[np.ndarray, int]:
    """使用 pydub 加载 MP3 等压缩格式."""
    segment = AudioSegment.from_file(str(file_path))

    # 设置参数
    if mono:
        segment = segment.set_channels(1)
    if segment.frame_rate != target_sr:
        segment = segment.set_frame_rate(target_sr)

    # 转为 numpy
    samples = np.array(segment.get_array_of_samples(), dtype=np.float32)

    # 归一化到 [-1, 1]
    max_val = float(2 ** (segment.sample_width * 8 - 1))
    samples = samples / max_val

    # reshape 为 (channels, samples)
    if segment.channels > 1:
        samples = samples.reshape(-1, segment.channels).T
    else:
        samples = samples.reshape(1, -1)

    return samples, target_sr


def save_audio(
    audio: np.ndarray,
    file_path: str | Path,
    sample_rate: int = 44100,
    subtype: str | None = None,
) -> Path:
    """保存音频到文件 / Save audio array to file.

    Args:
        audio: numpy array, shape=(n_samples,) 或 (n_channels, n_samples)
        file_path: 输出路径
        sample_rate: 采样率 Hz
        subtype: 音频子类型 ('PCM_16' | 'FLOAT' | None=自动)

    Returns:
        输出文件路径
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 确保格式正确: soundfile 需要 (samples, channels)
    if audio.ndim == 2:
        audio = audio.T  # (channels, samples) → (samples, channels)

    sf.write(str(file_path), audio, sample_rate, subtype=subtype)
    return file_path


def get_audio_info(file_path: str | Path) -> dict[str, float | int]:
    """获取音频文件信息 / Get audio file metadata.

    Returns:
        dict with keys: duration_sec, sample_rate, channels, frames
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    # MP3/M4A/AAC → soundfile 不支持，用 pydub
    if suffix in (".mp3", ".m4a", ".aac"):
        segment = AudioSegment.from_file(str(file_path))
        return {
            "duration_sec": len(segment) / 1000.0,
            "sample_rate": segment.frame_rate,
            "channels": segment.channels,
            "frames": len(segment),
        }

    info = sf.info(str(file_path))
    return {
        "duration_sec": info.duration,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
    }


def validate_audio(
    file_path: str | Path,
    max_duration_sec: float = 600.0,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, bool | str]:
    """验证音频文件可用性 / Validate audio file.

    Args:
        file_path: 音频文件路径
        max_duration_sec: 最大允许时长 (秒)

    Returns:
        {"valid": bool, "reason": str}
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return {"valid": False, "reason": f"文件不存在: {file_path}"}

    suffix = file_path.suffix.lower()
    supported = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    if suffix not in supported:
        return {"valid": False, "reason": f"不支持的格式: {suffix}, 支持: {supported}"}

    try:
        if progress_callback:
            progress_callback(10, "检查音频文件...")

        info = get_audio_info(str(file_path))

        if info["duration_sec"] <= 0:
            return {"valid": False, "reason": "音频长度为 0，文件可能损坏"}

        if info["duration_sec"] > max_duration_sec:
            return {
                "valid": False,
                "reason": f"音频过长: {info['duration_sec']:.1f}秒 > {max_duration_sec}秒 (最大)",
            }

        if progress_callback:
            progress_callback(100, "音频文件验证通过")

        return {"valid": True, "reason": "OK"}

    except Exception as e:
        return {"valid": False, "reason": f"无法读取音频: {e}"}


def is_silent(audio: np.ndarray, threshold_db: float = -60.0) -> bool:
    """检测音频是否接近静音 / Check if audio is near-silent.

    Args:
        audio: numpy array
        threshold_db: 静音阈值 (dB)

    Returns:
        True = 近似静音
    """
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-10:
        return True
    db = 20 * np.log10(rms)
    return db < threshold_db


def trim_silence(
    audio: np.ndarray,
    sample_rate: int = 44100,
    threshold_db: float = -40.0,
    min_duration_sec: float = 0.1,
) -> np.ndarray:
    """裁剪首尾静音 / Trim leading and trailing silence.

    Args:
        audio: numpy array
        sample_rate: 采样率
        threshold_db: 判定为静音的分贝阈值
        min_duration_sec: 保留的最小音频长度
    """
    # librosa.effects.trim expects (samples,) or (..., samples)
    trimmed, _ = librosa.effects.trim(
        audio,
        top_db=-threshold_db,
        frame_length=2048,
        hop_length=512,
    )
    # Ensure minimum duration
    min_samples = int(min_duration_sec * sample_rate)
    if trimmed.shape[-1] < min_samples:
        return audio  # Too short, return original
    return trimmed
