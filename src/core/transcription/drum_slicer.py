"""鼓组采样切片 / Drum sample slicer.

从鼓组分轨中检测打击事件，提取 one-shot 采样切片。
不做 MIDI 转录，不做音色匹配 — 直接保留原始音频片段。

分类: Kick / Snare / Hi-hat / Tom / Cymbal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import librosa
import soundfile


# === Drum type classification features ===
# (centroid_low, centroid_high, duration_range_ms, decay_factor)
DRUM_PROFILES = {
    "kick": {
        "name_zh": "底鼓",
        "freq_range": (30, 120),       # 低频为主
        "duration_range": (0.1, 0.6),   # 较长衰减
        "centroid_max": 800,            # 频谱质心低
    },
    "snare": {
        "name_zh": "军鼓",
        "freq_range": (150, 400),
        "duration_range": (0.05, 0.3),
        "centroid_min": 800,
        "centroid_max": 4000,
    },
    "hihat": {
        "name_zh": "踩镲",
        "freq_range": (3000, 12000),
        "duration_range": (0.02, 0.2),
        "centroid_min": 4000,
    },
    "tom": {
        "name_zh": "通鼓",
        "freq_range": (80, 600),
        "duration_range": (0.1, 0.5),
        "centroid_min": 200,
        "centroid_max": 2000,
    },
    "cymbal": {
        "name_zh": "镲片",
        "freq_range": (4000, 16000),
        "duration_range": (0.3, 3.0),
        "centroid_min": 3000,
    },
}


@dataclass
class DrumSlice:
    """单个鼓组采样切片 / A single drum one-shot slice."""

    index: int                # 切片序号
    onset_time: float         # 起始时间 (秒)
    onset_sample: int         # 起始采样点
    audio: np.ndarray         # 波形数据
    sample_rate: int          # 采样率
    drum_type: str            # 鼓类型: kick/snare/hihat/tom/cymbal/unknown
    drum_type_zh: str         # 中文鼓类型
    confidence: float         # 分类置信度 (0-1)
    peak_amplitude: float     # 峰值幅度
    duration_ms: float        # 持续时间 (ms)


@dataclass
class DrumSliceResult:
    """鼓组切片结果 / Result of drum slicing."""

    slices: list[DrumSlice] = field(default_factory=list)
    slice_count_by_type: dict[str, int] = field(default_factory=dict)
    output_dir: Optional[Path] = None

    @property
    def total_slices(self) -> int:
        return len(self.slices)

    def summary(self) -> str:
        lines = [f"检测到 {self.total_slices} 个打击事件:"]
        for dtype, count in sorted(self.slice_count_by_type.items()):
            profile = DRUM_PROFILES.get(dtype, {})
            zh = profile.get("name_zh", dtype)
            lines.append(f"  [{zh}] ({dtype}): {count} 个")
        return "\n".join(lines)


def detect_onsets(
    audio: np.ndarray,
    sr: int,
    hop_length: int = 512,
    backtrack: bool = True,
) -> np.ndarray:
    """检测音频中的打击起始点 / Detect drum onsets.

    Args:
        audio: 单声道音频数组
        sr: 采样率
        hop_length: 帧跳跃长度
        backtrack: 回溯到能量上升点

    Returns:
        起始点帧索引数组
    """
    # 使用 librosa 的 onset 检测，对打击乐优化
    onset_frames = librosa.onset.onset_detect(
        y=audio,
        sr=sr,
        hop_length=hop_length,
        backtrack=backtrack,
        units="frames",
        # 打击乐偏好: 较短窗口 + 较高阈值
        wait=int(0.03 * sr / hop_length),   # 最小间隔 30ms
        pre_max=int(0.005 * sr / hop_length),  # 前向窗口
        post_max=int(0.005 * sr / hop_length + 1),
        pre_avg=int(0.05 * sr / hop_length),
        post_avg=int(0.05 * sr / hop_length + 1),
        delta=0.15,  # 灵敏度
    )
    return onset_frames


def classify_drum_slice(
    audio_slice: np.ndarray,
    sr: int,
) -> tuple[str, str, float]:
    """分类单个鼓组采样切片 / Classify a drum one-shot slice.

    使用频谱质心 + 频带能量比 + 持续时间进行简单分类。

    Args:
        audio_slice: 切片音频数据
        sr: 采样率

    Returns:
        (drum_type_en, drum_type_zh, confidence)
    """
    if len(audio_slice) == 0:
        return ("unknown", "未知", 0.0)

    # 频谱质心
    centroid = np.abs(librosa.feature.spectral_centroid(
        y=audio_slice, sr=sr
    )).mean()

    # 频带能量比
    fft = np.abs(np.fft.rfft(audio_slice))
    freqs = np.fft.rfftfreq(len(audio_slice), 1.0 / sr)

    def band_energy(lo, hi):
        mask = (freqs >= lo) & (freqs < hi)
        return np.sum(fft[mask]) / (np.sum(fft) + 1e-10)

    low_energy = band_energy(20, 150)
    mid_energy = band_energy(150, 2000)
    high_energy = band_energy(2000, 16000)

    # 持续时间
    duration = len(audio_slice) / sr

    # 峰值幅度
    peak = np.max(np.abs(audio_slice))

    # 简单的规则分类
    if centroid < 800 and low_energy > 0.5:
        return ("kick", "底鼓", min(0.6 + low_energy * 0.4, 1.0))
    elif centroid > 6000 and high_energy > 0.6 and duration < 0.25:
        return ("hihat", "踩镲", min(0.6 + high_energy * 0.4, 1.0))
    elif centroid > 4000 and duration > 0.3:
        return ("cymbal", "镲片", 0.6 + high_energy * 0.3)
    elif 800 < centroid < 4000 and mid_energy > 0.4:
        # 区分 snare vs tom: snare 高频更多, 持续时间更短
        if high_energy > 0.15 and duration < 0.25:
            return ("snare", "军鼓", 0.65)
        else:
            return ("tom", "通鼓", 0.55)
    elif low_energy > 0.4:
        return ("kick", "底鼓", 0.5)
    else:
        return ("unknown", "未知", 0.3)


def slice_drum_stem(
    audio_path: Path,
    output_dir: Optional[Path] = None,
    min_slice_duration_s: float = 0.03,
    max_slice_duration_s: float = 1.0,
    onset_sensitivity: float = 0.15,
    save_slices: bool = True,
    save_by_type: bool = True,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> DrumSliceResult:
    """对鼓组 stem 进行采样切片 / Slice a drum stem into one-shot samples.

    Args:
        audio_path: 鼓组音频文件路径
        output_dir: 切片输出目录 (None = 自动创建 {stem_name}_slices/)
        min_slice_duration_s: 最短切片时长 (秒)
        max_slice_duration_s: 最长切片时长 (秒)
        onset_sensitivity: 起始检测灵敏度 (0-1, 越低越敏感)
        save_slices: 是否保存 WAV 文件
        save_by_type: 是否按鼓类型分子文件夹保存
        progress_callback: 进度回调 (percent, message)

    Returns:
        DrumSliceResult 包含所有切片信息
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    if progress_callback:
        progress_callback(5, "加载鼓组音频...")

    # 加载音频
    audio, sr = librosa.load(str(audio_path), sr=None, mono=True)

    if progress_callback:
        progress_callback(10, f"采样率: {sr}Hz, 时长: {len(audio)/sr:.1f}s")

    # 检测起始点
    if progress_callback:
        progress_callback(15, "检测打击事件...")

    hop_length = 512
    onset_frames = detect_onsets(audio, sr, hop_length=hop_length)

    n_onsets = len(onset_frames)
    if progress_callback:
        progress_callback(25, f"检测到 {n_onsets} 个候选事件")

    # 转换 onset 帧 → 采样点
    onset_samples = librosa.frames_to_samples(onset_frames, hop_length=hop_length)

    # 准备输出目录
    if save_slices:
        out_dir = output_dir or audio_path.parent / f"{audio_path.stem}_slices"
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = None

    # 切片处理
    slices = []
    type_counts: dict[str, int] = {}

    total = n_onsets
    slice_duration_samples = int(max_slice_duration_s * sr)

    for idx, onset_sample in enumerate(onset_samples):
        # 提取切片
        start = onset_sample
        end = min(start + slice_duration_samples, len(audio))
        audio_slice = audio[start:end]

        # 找到实际衰减结束点
        decay_end = _find_decay_end(audio_slice, sr, min_slice_duration_s)

        if decay_end < int(min_slice_duration_s * sr):
            continue  # 切片太短，跳过

        audio_slice = audio_slice[:decay_end]

        # 分类
        drum_type, drum_type_zh, confidence = classify_drum_slice(audio_slice, sr)

        # 峰值幅度
        peak = float(np.max(np.abs(audio_slice)))

        # 创建 DrumSlice
        onset_time = librosa.samples_to_time(onset_sample, sr=sr)
        drum_slice = DrumSlice(
            index=idx + 1,
            onset_time=onset_time,
            onset_sample=onset_sample,
            audio=audio_slice,
            sample_rate=sr,
            drum_type=drum_type,
            drum_type_zh=drum_type_zh,
            confidence=confidence,
            peak_amplitude=peak,
            duration_ms=len(audio_slice) / sr * 1000,
        )
        slices.append(drum_slice)
        type_counts[drum_type] = type_counts.get(drum_type, 0) + 1

        # 保存 WAV
        if save_slices and out_dir:
            if save_by_type:
                type_dir = out_dir / drum_type
                type_dir.mkdir(parents=True, exist_ok=True)
                save_path = type_dir / f"{drum_type}_{idx+1:03d}.wav"
            else:
                save_path = out_dir / f"slice_{idx+1:03d}_{drum_type}.wav"
            soundfile.write(str(save_path), audio_slice, sr)

        # 进度
        if progress_callback and idx % 10 == 0:
            pct = 25 + int((idx + 1) / total * 70)
            progress_callback(pct, f"切片 {idx+1}/{total}: {drum_type_zh}")

    result = DrumSliceResult(
        slices=slices,
        slice_count_by_type=type_counts,
        output_dir=out_dir,
    )

    if progress_callback:
        progress_callback(100, f"完成: {result.total_slices} 个切片 ({len(type_counts)} 类)")

    return result


def _find_decay_end(
    audio_slice: np.ndarray,
    sr: int,
    min_duration_s: float,
    threshold_ratio: float = 0.15,
) -> int:
    """找到音频切片的衰减结束点 / Find where the drum hit decays.

    Args:
        audio_slice: 音频切片
        sr: 采样率
        min_duration_s: 最短保持时长
        threshold_ratio: 包络阈值比例

    Returns:
        衰减结束的采样点索引
    """
    min_samples = int(min_duration_s * sr)

    if len(audio_slice) <= min_samples:
        return len(audio_slice)

    # 计算 RMS 包络
    frame_len = 256
    hop_len = 128
    rms = librosa.feature.rms(
        y=audio_slice, frame_length=frame_len, hop_length=hop_len
    )[0]
    rms = np.concatenate([rms, np.zeros(1)])  # 防止索引溢出

    peak_rms = np.max(rms)
    if peak_rms < 1e-8:
        return min_samples

    threshold = peak_rms * threshold_ratio

    # 从峰值之后找到衰减到阈值以下的点
    peak_frame = np.argmax(rms)
    for i in range(peak_frame, len(rms)):
        if rms[i] < threshold:
            # 返回这个点对应的采样位置，但至少保持 min_duration
            decay_sample = min(i * hop_len + frame_len, len(audio_slice))
            return max(decay_sample, min_samples)

    return len(audio_slice)


def export_drum_kit(
    result: DrumSliceResult,
    output_dir: Path,
    top_n_per_type: int = 8,
) -> dict[str, list[Path]]:
    """导出最佳鼓组采样作为精简鼓组 / Export best slices as a drum kit.

    每种类型选取音量最响的 top_n 个采样。

    Args:
        result: 切片结果
        output_dir: 导出目录
        top_n_per_type: 每种类型保留几个最佳采样

    Returns:
        {drum_type: [file_paths]}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported: dict[str, list[Path]] = {}

    for drum_type in ["kick", "snare", "hihat", "tom", "cymbal"]:
        type_slices = [s for s in result.slices if s.drum_type == drum_type]
        if not type_slices:
            continue

        # 按峰值幅度排序，取最大的几个
        type_slices.sort(key=lambda s: s.peak_amplitude, reverse=True)
        best = type_slices[:top_n_per_type]

        exported[drum_type] = []
        for i, ds in enumerate(best):
            path = output_dir / f"{drum_type}_{i+1:02d}.wav"
            soundfile.write(str(path), ds.audio, ds.sample_rate)
            exported[drum_type].append(path)

    return exported
