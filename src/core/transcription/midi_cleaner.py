"""MIDI 后处理 / MIDI post-processing & cleaning.

对 basic-pitch 转录的 MIDI 进行后处理:
- 量化 (snap to grid)
- 去噪 (移除碎音/鬼音)
- 合并 (融合重叠的同音音符)
- 力度归一化
- 速度/调性分析
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pretty_midi


@dataclass
class CleanConfig:
    """MIDI 清洗配置 / Cleaning configuration."""

    # 量化
    quantize_enabled: bool = True
    quantize_grid: float = 1/16  # 量化网格 (拍数), 默认 16 分音符
    quantize_strength: float = 0.7  # 量化强度 (0=不量化, 1=完全量化)

    # 去噪
    remove_short_notes: bool = True
    min_note_duration_ms: float = 40.0  # 最短音符 (ms)
    remove_quiet_notes: bool = True
    min_velocity: int = 15  # 最小力度
    remove_isolated_notes: bool = True
    isolated_note_gap_ms: float = 500.0  # 孤立音符判定间隔

    # 合并
    merge_overlapping: bool = True
    merge_gap_ms: float = 30.0  # 允许合并的最大间隙 (ms)

    # 力度
    normalize_velocity: bool = True
    target_mean_velocity: int = 90  # 目标平均力度
    max_velocity: int = 120

    # 音域限制
    min_pitch: Optional[int] = None  # 最低 MIDI 音高
    max_pitch: Optional[int] = None  # 最高 MIDI 音高


@dataclass
class CleanReport:
    """清洗报告 / Cleaning report."""

    original_note_count: int = 0
    cleaned_note_count: int = 0
    removed_short: int = 0
    removed_quiet: int = 0
    removed_isolated: int = 0
    merged_count: int = 0
    estimated_tempo: Optional[float] = None
    estimated_key: Optional[str] = None

    def summary(self) -> str:
        lines = [
            f"原始音符: {self.original_note_count}",
            f"清洗后:   {self.cleaned_note_count}",
        ]
        if self.removed_short:
            lines.append(f"  移除过短: {self.removed_short}")
        if self.removed_quiet:
            lines.append(f"  移除过弱: {self.removed_quiet}")
        if self.removed_isolated:
            lines.append(f"  移除孤立: {self.removed_isolated}")
        if self.merged_count:
            lines.append(f"  合并重叠: {self.merged_count}")
        if self.estimated_tempo:
            lines.append(f"  估计速度: {self.estimated_tempo:.0f} BPM")
        if self.estimated_key:
            lines.append(f"  估计调性: {self.estimated_key}")
        return "\n".join(lines)


def clean_midi(
    midi_data: pretty_midi.PrettyMIDI,
    config: Optional[CleanConfig] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> tuple[pretty_midi.PrettyMIDI, CleanReport]:
    """清洗 MIDI 数据 / Clean and post-process MIDI data.

    Args:
        midi_data: 原始 pretty_midi.PrettyMIDI 对象
        config: 清洗配置 (None = 使用默认)
        progress_callback: 进度回调

    Returns:
        (cleaned_midi, report)
    """
    if config is None:
        config = CleanConfig()

    report = CleanReport()

    if progress_callback:
        progress_callback(5, "统计原始音符...")

    # 统计原始音符数
    for instr in midi_data.instruments:
        report.original_note_count += len(instr.notes)

    # 创建新的 MIDI 对象
    cleaned = pretty_midi.PrettyMIDI(initial_tempo=midi_data.get_tempo_changes()[1][0]
                                     if len(midi_data.get_tempo_changes()[1]) > 0 else 120)

    piano_program = pretty_midi.instrument_name_to_program("Electric Piano 1")
    new_instrument = pretty_midi.Instrument(program=piano_program)

    # 收集所有音符 (扁平化)
    all_notes: list[tuple[int, pretty_midi.Note]] = []
    for instr in midi_data.instruments:
        for note in instr.notes:
            all_notes.append((0, note))  # instrument_index 暂不用

    if progress_callback:
        progress_callback(10, f"处理 {len(all_notes)} 个音符...")

    # ---- 步骤 1: 去噪 (移除碎音/弱音) ----
    cleaned_notes = []
    for _, note in all_notes:
        duration_ms = (note.end - note.start) * 1000

        # 移除过短音符
        if config.remove_short_notes and duration_ms < config.min_note_duration_ms:
            report.removed_short += 1
            continue

        # 移除过弱音符
        if config.remove_quiet_notes and note.velocity < config.min_velocity:
            report.removed_quiet += 1
            continue

        cleaned_notes.append(note)

    if progress_callback:
        progress_callback(30, f"去噪后剩余 {len(cleaned_notes)} 个音符")

    # ---- 步骤 2: 移除孤立音符 ----
    if config.remove_isolated_notes:
        gap_sec = config.isolated_note_gap_ms / 1000
        cleaned_notes.sort(key=lambda n: n.start)

        not_isolated = []
        for i, note in enumerate(cleaned_notes):
            is_isolated = True
            if i > 0:
                prev_end = cleaned_notes[i - 1].end
                if note.start - prev_end < gap_sec:
                    is_isolated = False
            if i < len(cleaned_notes) - 1:
                next_start = cleaned_notes[i + 1].start
                if next_start - note.end < gap_sec:
                    is_isolated = False
            if is_isolated:
                report.removed_isolated += 1
            else:
                not_isolated.append(note)
        cleaned_notes = not_isolated

    if progress_callback:
        progress_callback(45, f"移除孤立音符: {report.removed_isolated}")

    # ---- 步骤 3: 合并重叠同音音符 ----
    if config.merge_overlapping:
        merge_gap = config.merge_gap_ms / 1000
        # 按音高分组
        by_pitch: dict[int, list[pretty_midi.Note]] = {}
        for note in cleaned_notes:
            by_pitch.setdefault(note.pitch, []).append(note)

        merged_notes = []
        for pitch, notes in by_pitch.items():
            notes.sort(key=lambda n: n.start)
            current = notes[0]
            for next_note in notes[1:]:
                if next_note.start - current.end <= merge_gap:
                    # 合并: 扩展结束时间, 取平均力度
                    current.end = max(current.end, next_note.end)
                    current.velocity = int((current.velocity + next_note.velocity) / 2)
                    report.merged_count += 1
                else:
                    merged_notes.append(current)
                    current = next_note
            merged_notes.append(current)
        cleaned_notes = merged_notes

    if progress_callback:
        progress_callback(60, f"合并后: {len(cleaned_notes)} 个音符")

    # ---- 步骤 4: 量化 ----
    if config.quantize_enabled:
        # 以 tempo 计算网格
        tempo = _estimate_tempo(midi_data)
        beat_duration = 60.0 / tempo  # 一拍多少秒
        grid = config.quantize_grid * beat_duration  # 网格大小 (秒)

        for note in cleaned_notes:
            # 量化起始时间
            original_start = note.start
            quantized_start = round(note.start / grid) * grid
            note.start = (
                original_start * (1 - config.quantize_strength)
                + quantized_start * config.quantize_strength
            )

            # 量化结束时间
            original_end = note.end
            quantized_end = round(note.end / grid) * grid
            note.end = (
                original_end * (1 - config.quantize_strength)
                + quantized_end * config.quantize_strength
            )

            # 确保 note 不倒退
            if note.end <= note.start:
                note.end = note.start + grid

        report.estimated_tempo = tempo

    if progress_callback:
        progress_callback(75, "量化完成")

    # ---- 步骤 5: 力度归一化 ----
    if config.normalize_velocity and cleaned_notes:
        velocities = [n.velocity for n in cleaned_notes]
        current_mean = np.mean(velocities)
        if current_mean > 0:
            scale = config.target_mean_velocity / current_mean
            for note in cleaned_notes:
                note.velocity = min(
                    int(note.velocity * scale),
                    config.max_velocity,
                )
                note.velocity = max(note.velocity, 1)

    # ---- 步骤 6: 音域过滤 ----
    if config.min_pitch is not None or config.max_pitch is not None:
        cleaned_notes = [
            n for n in cleaned_notes
            if (config.min_pitch is None or n.pitch >= config.min_pitch)
            and (config.max_pitch is None or n.pitch <= config.max_pitch)
        ]

    # ---- 组装输出 ----
    for note in sorted(cleaned_notes, key=lambda n: n.start):
        new_instrument.notes.append(note)

    cleaned.instruments.append(new_instrument)

    # 估算调性
    if cleaned_notes:
        report.estimated_key = _estimate_key(cleaned_notes)

    report.cleaned_note_count = len(cleaned_notes)

    if progress_callback:
        progress_callback(100, f"清洗完成: {report.cleaned_note_count} 个音符")

    return cleaned, report


def _estimate_tempo(midi_data: pretty_midi.PrettyMIDI) -> float:
    """从 MIDI 数据估算速度 / Estimate tempo from MIDI."""
    tempo_changes = midi_data.get_tempo_changes()
    if len(tempo_changes[1]) > 0:
        return float(tempo_changes[1][0])
    return 120.0


def _estimate_key(notes: list[pretty_midi.Note]) -> str:
    """简单调性估算 / Simple key estimation based on pitch class distribution.

    Args:
        notes: 音符列表

    Returns:
        调性名称 (如 "C", "G", "Am")
    """
    if not notes:
        return "?"

    # 统计 12 音名出现频次 (加权时长)
    pitch_counts = np.zeros(12)
    for note in notes:
        duration = note.end - note.start
        pitch_class = note.pitch % 12
        pitch_counts[pitch_class] += duration

    if pitch_counts.sum() == 0:
        return "?"

    pitch_counts /= pitch_counts.sum()

    # 大调模板
    MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.03, 1.23, 4.12, 4.28])
    MAJOR_PROFILE = MAJOR_PROFILE / MAJOR_PROFILE.sum()

    # 小调模板
    MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 5.01])
    MINOR_PROFILE = MINOR_PROFILE / MINOR_PROFILE.sum()

    PITCH_NAMES_MAJOR = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    PITCH_NAMES_MINOR = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]

    # 找最佳匹配
    best_major_score = -1
    best_minor_score = -1
    best_major = 0
    best_minor = 0

    for tonic in range(12):
        rolled = np.roll(pitch_counts, -tonic)
        major_score = np.corrcoef(rolled, MAJOR_PROFILE)[0, 1]
        minor_score = np.corrcoef(rolled, MINOR_PROFILE)[0, 1]

        if major_score > best_major_score:
            best_major_score = major_score
            best_major = tonic
        if minor_score > best_minor_score:
            best_minor_score = minor_score
            best_minor = tonic

    if best_major_score >= best_minor_score:
        return PITCH_NAMES_MAJOR[best_major]
    else:
        return PITCH_NAMES_MINOR[best_minor]


def extract_tempo_map(
    midi_data: pretty_midi.PrettyMIDI,
) -> dict:
    """提取速度映射信息 / Extract tempo map from MIDI.

    Returns:
        {'initial_tempo': float, 'tempo_changes': [(time, tempo), ...]}
    """
    times, tempos = midi_data.get_tempo_changes()
    return {
        "initial_tempo": float(tempos[0]) if len(tempos) > 0 else 120.0,
        "tempo_changes": [(float(t), float(b)) for t, b in zip(times, tempos)],
    }


def get_midi_stats(midi_data: pretty_midi.PrettyMIDI) -> dict:
    """获取 MIDI 统计信息 / Get MIDI statistics.

    Returns:
        {'note_count': int, 'duration_s': float, 'pitch_range': (min, max),
         'mean_velocity': float, 'note_density': float (notes/sec)}
    """
    all_notes = []
    for instr in midi_data.instruments:
        all_notes.extend(instr.notes)

    if not all_notes:
        return {
            "note_count": 0,
            "duration_s": 0.0,
            "pitch_range": (0, 0),
            "mean_velocity": 0.0,
            "note_density": 0.0,
        }

    pitches = [n.pitch for n in all_notes]
    velocities = [n.velocity for n in all_notes]
    duration = max(n.end for n in all_notes)

    return {
        "note_count": len(all_notes),
        "duration_s": round(duration, 2),
        "pitch_range": (min(pitches), max(pitches)),
        "mean_velocity": round(float(np.mean(velocities)), 1),
        "note_density": round(len(all_notes) / duration, 2) if duration > 0 else 0.0,
    }
