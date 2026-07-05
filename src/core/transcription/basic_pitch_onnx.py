"""Basic Pitch ONNX 推理封装 / ONNX-based transcription wrapper.

Uses Spotify's basic-pitch model via ONNX Runtime — zero TensorFlow dependency.
The model takes raw audio (22050 Hz mono) and outputs note/onset/contour
activations, which are then decoded into MIDI note events.

Reference: ICASSP 2022 — "Basic Pitch: A Lightweight Neural Network for
Automatic Music Transcription"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np

# ---- lazy imports: basic_pitch triggers TF/onnx checks at import time ----
_predict_fn = None
_MODEL_CACHE = None


def _get_predict_fn():
    """Lazy-load basic_pitch predict function (avoids import overhead)."""
    global _predict_fn
    if _predict_fn is None:
        # 抑制 basic_pitch 启动时的 TF 警告 (我们只用 ONNX)
        logging.getLogger("root").setLevel(logging.ERROR)
        from basic_pitch.inference import predict, Model
        from basic_pitch import ICASSP_2022_MODEL_PATH as _BP_MODEL_PATH

        logging.getLogger("root").setLevel(logging.WARNING)

        # 优先使用 ONNX 模型
        import basic_pitch
        if basic_pitch.ONNX_PRESENT:
            from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
            _model_path = build_icassp_2022_model_path(FilenameSuffix.onnx)
        else:
            _model_path = _BP_MODEL_PATH

        _predict_fn = (predict, Model, _model_path)
    return _predict_fn


def transcribe(
    audio_path: Path,
    output_dir: Optional[Path] = None,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length: float = 58.0,  # ms, 原始默认 127.70 偏保守
    minimum_frequency: Optional[float] = None,
    maximum_frequency: Optional[float] = None,
    melodia_trick: bool = True,
    midi_tempo: float = 120,
    bpm: Optional[float] = None,  # 外部检测的 BPM，优先于 midi_tempo
    save_midi: bool = True,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """对音频文件执行 MIDI 转录 / Transcribe audio to MIDI.

    Args:
        audio_path: 输入音频文件路径 (WAV/MP3/FLAC, 自动转 mono 22050Hz)
        output_dir: MIDI 输出目录 (None = 同音频目录)
        onset_threshold: 起音阈值 (0-1), 越高越严格
        frame_threshold: 持续帧阈值 (0-1)
        minimum_note_length: 最短音符长度 (ms), 滤除碎音
        minimum_frequency: 最低频率限制 (Hz), None = 不限
        maximum_frequency: 最高频率限制 (Hz), None = 不限
        melodia_trick: 启用 Melodia 补充检测 (推荐)
        midi_tempo: MIDI 文件速度 (BPM), 默认 120 (当 bpm 不为 None 时被覆盖)
        bpm: 外部节拍检测的 BPM (如 BeatDetector), 优先于 midi_tempo.
            为 None 时使用 midi_tempo 的默认行为。
        save_midi: 是否保存 .mid 文件
        progress_callback: 进度回调 (percent, message)

    Returns:
        {
            'midi_path': Path | None,       # MIDI 文件路径
            'midi_data': PrettyMIDI,         # pretty_midi 对象
            'note_events': list[tuple],       # (start_s, end_s, pitch, velocity, pitch_bends)
            'model_output': dict,             # 原始模型输出 {'note', 'onset', 'contour'}
        }
    """
    predict_fn, _Model, model_path = _get_predict_fn()

    if progress_callback:
        progress_callback(10, "加载 basic-pitch ONNX 模型...")

    # 运行推理与解码
    model_output, midi_data, note_events = predict_fn(
        str(audio_path),
        model_or_model_path=model_path,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=minimum_note_length,
        minimum_frequency=minimum_frequency,
        maximum_frequency=maximum_frequency,
        multiple_pitch_bends=False,
        melodia_trick=melodia_trick,
        midi_tempo=bpm if bpm is not None else midi_tempo,
    )

    if progress_callback:
        progress_callback(80, f"转录完成: {len(note_events)} 个音符")

    # 保存 MIDI 文件
    midi_path = None
    if save_midi:
        out_dir = output_dir or audio_path.parent
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        midi_path = out_dir / f"{audio_path.stem}_transcribed.mid"
        midi_data.write(str(midi_path))

        if progress_callback:
            progress_callback(100, f"MIDI 已保存: {midi_path.name}")

    return {
        "midi_path": midi_path,
        "midi_data": midi_data,
        "note_events": note_events,
        "model_output": model_output,
    }


def get_note_count(midi_data) -> int:
    """获取 MIDI 中的总音符数 / Get total note count."""
    return sum(len(instr.notes) for instr in midi_data.instruments)


def get_pitch_range(midi_data) -> tuple[int, int]:
    """获取 MIDI 音高范围 (min, max) / Get pitch range."""
    all_pitches = []
    for instr in midi_data.instruments:
        for note in instr.notes:
            all_pitches.append(note.pitch)
    if not all_pitches:
        return (0, 0)
    return (min(all_pitches), max(all_pitches))


def get_note_density(midi_data) -> float:
    """获取音符密度 (音符数/秒) / Get note density (notes/sec)."""
    all_notes = []
    for instr in midi_data.instruments:
        all_notes.extend(instr.notes)
    if not all_notes:
        return 0.0
    total_time = max(n.end for n in all_notes)
    if total_time == 0:
        return 0.0
    return len(all_notes) / total_time
