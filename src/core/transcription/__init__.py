"""MIDI 转录模块 / MIDI transcription module.

Phase 2 — 分轨音频 → MIDI 文件 + 鼓组采样切片
"""

from src.core.transcription.basic_pitch_onnx import transcribe, get_note_count
from src.core.transcription.drum_slicer import slice_drum_stem, export_drum_kit
from src.core.transcription.midi_cleaner import clean_midi, CleanConfig, CleanReport

__all__ = [
    "transcribe",
    "get_note_count",
    "slice_drum_stem",
    "export_drum_kit",
    "clean_midi",
    "CleanConfig",
    "CleanReport",
]
