"""节奏型分析与碎音检测 / Rhythmic Pattern Analysis & Spurious Note Detection.

基于节拍分析结果，对量化后的 MIDI 进行:
- 节奏型指纹提取 (per-beat pattern fingerprinting)
- 碎音标记 (仅出现一次的短时值节奏型 → 可疑)
- 碎音合并 (吸附到相邻同音高音符)
- 分段复核 (每 N 小节检查拍位对齐率)

核心假设:
    音乐中的节奏型通常是重复的。仅出现一次且时值 ≤ 16 分音符的
    节奏型很可能是 basic-pitch 的转录误差 (泛音/噪音误识别)。

用法:
    from src.core.analysis import AnalysisResult
    from src.core.analysis.rhythm_analyzer import (
        RhythmReport, extract_rhythmic_patterns,
        flag_spurious_notes, merge_flagged_notes, section_review,
    )

    patterns = extract_rhythmic_patterns(midi_data, analysis)
    flagged = flag_spurious_notes(midi_data, patterns, min_occurrences=2)
    cleaned = merge_flagged_notes(midi_data, flagged, analysis)
    warnings = section_review(midi_data, analysis, interval_bars=16)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pretty_midi

from src.core.analysis.beat_detector import AnalysisResult


# ===== 数据类型 =====

@dataclass
class RhythmReport:
    """节奏分析报告 / Rhythm analysis report.

    Attributes:
        total_patterns: 发现的独特节奏型总数
        rare_pattern_count: 出现次数 ≤ 阈值的节奏型数
        flagged_notes: 被标记为可疑的音符数
        merged_notes: 被合并/移除的音符数
        section_warnings: 分段复核警告列表
        pattern_counts: {pattern_fingerprint: occurrence_count}
    """
    total_patterns: int = 0
    rare_pattern_count: int = 0
    flagged_notes: int = 0
    merged_notes: int = 0
    section_warnings: list[str] = field(default_factory=list)
    pattern_counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """生成中文摘要 / Generate Chinese summary."""
        lines = [
            f"节奏型总数: {self.total_patterns}",
            f"稀有节奏型: {self.rare_pattern_count} (仅出现1-2次)",
            f"标记碎音:   {self.flagged_notes}",
            f"合并/移除:  {self.merged_notes}",
        ]
        if self.section_warnings:
            lines.append(f"拍位警告:   {len(self.section_warnings)} 段")
            for w in self.section_warnings:
                lines.append(f"  {w}")
        return "\n".join(lines)


# ===== 常量 =====

# 16 分音符网格 (每个 beat 分成 16 个位置)
GRID_DIVISIONS = 16
# 碎音候选: 短于这个时值 (ms) 的音符才考虑标记
DEFAULT_SHORT_THRESHOLD_MS = 150.0
# 最小出现次数: 模式出现次数 ≤ 此值视为稀有
DEFAULT_MIN_OCCURRENCES = 2
# 分段复核默认间隔 (bars)
DEFAULT_REVIEW_INTERVAL = 16
# 拍位对齐警告阈值: 超过此比例的音符偏离拍点则警告
ALIGNMENT_WARNING_PCT = 0.3


# ===== 公开 API =====

def extract_rhythmic_patterns(
    midi_data: pretty_midi.PrettyMIDI,
    analysis: AnalysisResult,
    quantize_grid: float = 1 / GRID_DIVISIONS,
) -> dict[str, list[int]]:
    """提取节奏型指纹 / Extract rhythmic pattern fingerprints.

    对每个 beat 内的 note onset 位置做量化，生成指纹字符串。
    例如: "0,4,8,12" 表示在一个 beat 内有 4 个 16 分音符。

    Args:
        midi_data: pretty_midi 对象 (已量化)
        analysis: 节拍分析结果 (包含 beat_times)
        quantize_grid: 每个 beat 的网格划分 (默认 1/16)

    Returns:
        {pattern_fingerprint: [note_index, ...]}
        其中 note_index 是在扁平化音符列表中的索引

    Raises:
        ValueError: analysis 不含有效的 beat_times
    """
    if not analysis.beat_times:
        raise ValueError("analysis.beat_times 为空，无法提取节奏型")

    # 扁平化所有音符
    all_notes: list[tuple[int, pretty_midi.Note]] = []
    for instr_idx, instr in enumerate(midi_data.instruments):
        for note in instr.notes:
            all_notes.append((instr_idx, note))

    if not all_notes:
        return {}

    all_notes.sort(key=lambda x: x[1].start)

    pattern_notes: dict[str, list[int]] = {}

    for note_idx, (_, note) in enumerate(all_notes):
        onset = note.start
        # 找到该 onset 属于哪个 beat
        beat_idx = _find_beat(onset, analysis.beat_times)

        if beat_idx < 0 or beat_idx >= len(analysis.beat_times):
            continue

        beat_start = analysis.beat_times[beat_idx]
        # 该 beat 的结束时间 (下一个 beat 或最后一个 beat + beat_interval)
        if beat_idx + 1 < len(analysis.beat_times):
            beat_end = analysis.beat_times[beat_idx + 1]
        else:
            beat_end = beat_start + analysis.beat_interval

        # 计算 onset 在 beat 内的相对位置 (0-15 for 16th note grid)
        relative_pos = (onset - beat_start) / (beat_end - beat_start)
        # 量化到网格
        grid_pos = int(round(relative_pos * GRID_DIVISIONS)) % GRID_DIVISIONS

        # 组装指纹: "{beat_position_in_bar}:{grid_positions}"
        beat_in_bar = analysis.beat_positions[beat_idx] if beat_idx < len(analysis.beat_positions) else 0
        fingerprint = f"b{beat_in_bar}:{grid_pos}"

        if fingerprint not in pattern_notes:
            pattern_notes[fingerprint] = []
        pattern_notes[fingerprint].append(note_idx)

    return pattern_notes


def flag_spurious_notes(
    midi_data: pretty_midi.PrettyMIDI,
    patterns: dict[str, list[int]],
    analysis: Optional[AnalysisResult] = None,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    short_note_threshold_ms: float = DEFAULT_SHORT_THRESHOLD_MS,
) -> list[int]:
    """标记可疑碎音 / Flag potential spurious notes.

    规则:
    1. 节奏型在全曲中出现次数 ≤ min_occurrences → 可疑
    2. 该音符的时值 ≤ short_note_threshold_ms → 候选
    3. 同时满足 1+2 → 标记为碎音
    注意: 时值超过 16 分音符的长音符即使唯一也保留 (不像误差)。

    Args:
        midi_data: pretty_midi 对象
        patterns: extract_rhythmic_patterns() 的输出
        analysis: 节拍分析 (用于计算 16 分音符时值)
        min_occurrences: 模式最少出现次数 (≤ 此值标记为稀有)
        short_note_threshold_ms: 碎音最小时值 (ms)

    Returns:
        被标记的音符索引列表 (扁平化)
    """
    # 计算 16 分音符的时值 (ms)，作为动态阈值上限
    if analysis and analysis.bpm > 0:
        beat_ms = 60000.0 / analysis.bpm
        sixteenth_ms = beat_ms / 4.0  # 16 分音符 = 1/4 beat
        effective_threshold = min(short_note_threshold_ms, sixteenth_ms * 1.2)
    else:
        effective_threshold = short_note_threshold_ms

    # 扁平化音符
    all_notes: list[pretty_midi.Note] = []
    for instr in midi_data.instruments:
        all_notes.extend(instr.notes)

    flagged: set[int] = set()

    for fingerprint, note_indices in patterns.items():
        count = len(note_indices)

        if count > min_occurrences:
            continue  # 不稀有，跳过

        # 稀有模式: 检查其中的短音符
        for idx in note_indices:
            if idx >= len(all_notes):
                continue
            note = all_notes[idx]
            duration_ms = (note.end - note.start) * 1000

            if duration_ms <= effective_threshold:
                flagged.add(idx)

    return sorted(flagged)


def merge_flagged_notes(
    midi_data: pretty_midi.PrettyMIDI,
    flagged_indices: list[int],
    analysis: Optional[AnalysisResult] = None,
) -> pretty_midi.PrettyMIDI:
    """合并标记的音符到相邻同音高音符 / Merge flagged notes.

    对每个标记音符:
    1. 在 1 beat 范围内找同一音高的最近音符
    2. 如果找到, 延长其 end time 覆盖标记音符
    3. 如果没找到, 直接移除标记音符

    Args:
        midi_data: pretty_midi 对象 (原地修改 + 返回)
        flagged_indices: flag_spurious_notes() 的输出
        analysis: 节拍分析 (用于确定搜索范围)

    Returns:
        修改后的 midi_data (同时也是原地修改)
    """
    if not flagged_indices:
        return midi_data

    # 搜索范围: 1 beat (秒)
    if analysis and analysis.bpm > 0:
        search_radius = analysis.beat_interval
    else:
        search_radius = 0.5  # 默认 ~120 BPM 的 1 beat

    # 扁平化
    all_notes: list[pretty_midi.Note] = []
    for instr in midi_data.instruments:
        all_notes.extend(instr.notes)

    flagged_set = set(flagged_indices)
    notes_to_remove: set[int] = set()
    note_modifications: list[tuple[int, float]] = []  # (neighbor_idx, new_end)

    for idx in flagged_indices:
        if idx >= len(all_notes):
            continue
        flagged_note = all_notes[idx]
        pitch = flagged_note.pitch
        onset = flagged_note.start

        # 找最近的同音高音符 (非 flagged, 在 search_radius 内)
        best_neighbor = -1
        best_distance = float('inf')

        for other_idx, other_note in enumerate(all_notes):
            if other_idx in flagged_set:
                continue
            if other_note.pitch != pitch:
                continue
            # 距离 (时间差绝对值)
            dist = abs(other_note.start - onset)
            if dist < search_radius and dist < best_distance:
                best_distance = dist
                best_neighbor = other_idx

        if best_neighbor >= 0:
            # 延长 neighbor 的 end time 覆盖碎音
            neighbor = all_notes[best_neighbor]
            new_end = max(neighbor.end, flagged_note.end)
            if new_end > neighbor.end:
                note_modifications.append((best_neighbor, new_end))
            notes_to_remove.add(idx)
        else:
            # 找不到 neighbor → 直接移除
            notes_to_remove.add(idx)

    # 应用修改
    for neighbor_idx, new_end in note_modifications:
        all_notes[neighbor_idx].end = new_end

    # 从 instrument 中移除标记音符 (O(n) via set lookup, not O(n²))
    removed_ids = {id(all_notes[i]) for i in notes_to_remove}
    for instr in midi_data.instruments:
        instr.notes = [n for n in instr.notes if id(n) not in removed_ids]

    return midi_data


def section_review(
    midi_data: pretty_midi.PrettyMIDI,
    analysis: AnalysisResult,
    interval_bars: int = DEFAULT_REVIEW_INTERVAL,
    warning_threshold: float = ALIGNMENT_WARNING_PCT,
) -> list[str]:
    """分段复核拍位对齐 / Section-by-section beat alignment review.

    将乐曲划分为每 N 小节一段，检查每段内音符 onset 是否对齐到节拍网格。
    偏离比例 > warning_threshold 的段落生成警告。

    Args:
        midi_data: pretty_midi 对象
        analysis: 节拍分析结果
        interval_bars: 每段小节数 (16, 32, 64)
        warning_threshold: 偏离比例阈值 (0.3 = 30%)

    Returns:
        警告信息列表 (中文)
    """
    if not analysis.downbeat_times or not analysis.beat_times:
        return []

    # 收集所有音符 onset
    all_onsets = []
    for instr in midi_data.instruments:
        for note in instr.notes:
            all_onsets.append(note.start)

    if not all_onsets:
        return []

    # 总小节数
    total_bars = len(analysis.downbeat_times)
    if total_bars < interval_bars:
        # 乐曲太短，不分段 — 一段检查所有
        sections = [(0, total_bars)]
    else:
        sections = []
        for start_bar in range(0, total_bars, interval_bars):
            end_bar = min(start_bar + interval_bars, total_bars)
            sections.append((start_bar, end_bar))

    warnings: list[str] = []

    for section_start, section_end in sections:
        # 本段时间范围
        if section_start >= len(analysis.downbeat_times):
            continue
        t_start = analysis.downbeat_times[section_start]
        if section_end < len(analysis.downbeat_times):
            t_end = analysis.downbeat_times[section_end]
        else:
            # 最后一段: 到最后一个 downbeat + 1 bar
            t_end = analysis.downbeat_times[-1] + analysis.bar_interval

        # 统计本段内偏离拍点的音符
        total_in_section = 0
        off_grid = 0
        grid_tolerance = analysis.beat_interval / 8.0  # 32 分音符作为容差

        for onset in all_onsets:
            if t_start <= onset < t_end:
                total_in_section += 1
                # 找最近的节拍位置
                nearest_beat_dist = _distance_to_nearest_beat(onset, analysis.beat_times)
                if nearest_beat_dist > grid_tolerance:
                    off_grid += 1

        if total_in_section == 0:
            continue

        off_ratio = off_grid / total_in_section
        if off_ratio > warning_threshold:
            warnings.append(
                f"第 {section_start + 1}-{section_end} 小节: "
                f"{off_grid}/{total_in_section} 音符偏离拍位 ({off_ratio:.0%}), "
                f"建议复核"
            )

    return warnings


# ===== 内部辅助 =====

def _find_beat(onset_time: float, beat_times: list[float]) -> int:
    """找到 onset_time 属于哪个 beat (返回 beat index).

    Args:
        onset_time: 音符起始时间 (秒)
        beat_times: 节拍时间点列表

    Returns:
        beat index (0-indexed), -1 如果 onset 在所有 beat 之前
    """
    if not beat_times:
        return -1
    for i in range(len(beat_times) - 1):
        if beat_times[i] <= onset_time < beat_times[i + 1]:
            return i
    # 最后一个 beat 之后
    if onset_time >= beat_times[-1]:
        return len(beat_times) - 1
    return -1


def _distance_to_nearest_beat(onset: float, beat_times: list[float]) -> float:
    """计算 onset 到最近 beat 的距离 (秒) / Distance to nearest beat.

    Args:
        onset: 音符起始时间
        beat_times: 节拍时间点

    Returns:
        距离 (秒)
    """
    if not beat_times:
        return float('inf')
    # 二分查找
    import bisect
    idx = bisect.bisect_left(beat_times, onset)
    candidates = []
    if idx < len(beat_times):
        candidates.append(abs(beat_times[idx] - onset))
    if idx > 0:
        candidates.append(abs(beat_times[idx - 1] - onset))
    return min(candidates) if candidates else float('inf')
