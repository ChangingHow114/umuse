"""谱号与八度优化 / Clef and Octave Optimization.

根据乐器类型自动选择最佳谱号，并在极端音域段落添加 8va/8vb 标记。

支持:
- bass → Bass8vbClef (bass_8, 实际音高低八度, 谱面抬高显示)
- guitar → Treble8vbClef (treble_8, 实际音高低八度, 谱面抬高显示)
- piano/vocals → 自动从音域选择 TrebleClef 或 BassClef
- 连续极端音域段落 → 插入 8va/8vb spanner

用法:
    from src.core.notation.octave_optimizer import (
        optimize_clef_for_instrument, apply_ottava, get_instrument_clef,
    )
    score = optimize_clef_for_instrument(score, "bass")
    score = apply_ottava(score, high_threshold=79, low_threshold=48)
"""

from __future__ import annotations

from typing import Optional

import music21
from music21 import clef, instrument, spanner, stream


# ===== 阈值常量 (MIDI pitch) =====

# Bass 谱号判断: 平均音高低于此 → 使用 bass_8
BASS_8_MEAN_PITCH = 55        # G3
# 极端音域阈值
TREBLE_8VA_THRESHOLD = 79     # G5 — 高于此 → 考虑 8va
TREBLE_8VB_THRESHOLD = 48     # C3 — 低于此且非 bass → 考虑 8vb
# Ottava 最小连续小节数 (避免单小节孤立标记)
OTTAVA_MIN_MEASURES = 2

# 乐器 → 默认谱号映射
INSTRUMENT_CLEF_MAP: dict[str, type] = {
    "bass": clef.Bass8vbClef,    # bass_8 谱号
    "guitar": clef.Treble8vbClef,  # treble_8 谱号 (吉他实际音高低八度)
    "piano": clef.TrebleClef,     # 钢琴默认高音谱号
    "vocals": clef.TrebleClef,    # 人声默认高音谱号
    "other": clef.TrebleClef,
}


def get_instrument_clef(instrument_name: str) -> music21.clef.Clef:
    """获取乐器的最佳默认谱号 / Get optimal default clef for instrument.

    Args:
        instrument_name: 乐器名称 (如 'bass', 'guitar', 'piano', 'vocals')

    Returns:
        music21 Clef 对象
    """
    clef_cls = INSTRUMENT_CLEF_MAP.get(instrument_name.lower(), clef.TrebleClef)
    return clef_cls()


def optimize_clef_for_instrument(
    score: music21.stream.Score,
    instrument_name: str,
) -> music21.stream.Score:
    """为每个 Part 设置最佳谱号 / Assign optimal clef for each Part.

    根据乐器类型和实际音域：
    - bass → Bass8vbClef (bass_8)
    - guitar → Treble8vbClef (treble_8, 实际音高低八度)
    - piano/vocals → 自动从 pitch range 选择

    Args:
        score: music21 Score 对象 (原地修改 + 返回)
        instrument_name: 乐器名称

    Returns:
        修改后的 Score (同时也是原地修改)
    """
    inst_name_lower = instrument_name.lower()
    optimal_clef = get_instrument_clef(inst_name_lower)

    for part in score.parts:
        # 检查是否已有谱号
        has_clef = any(isinstance(el, clef.Clef) for el in part.recurse())

        if has_clef:
            # 替换第一个谱号
            for el in part.recurse():
                if isinstance(el, clef.Clef):
                    # 在相同位置替换 (music21 没有直接 replace, 用 remove+insert)
                    try:
                        offset = el.offset
                        part.remove(el)
                        part.insert(offset, optimal_clef)
                    except Exception:
                        pass
                    break
        else:
            # 没有谱号 → 在开头插入
            part.insert(0, optimal_clef)

    return score


def apply_ottava(
    score: music21.stream.Score,
    high_threshold_midi: int = TREBLE_8VA_THRESHOLD,
    low_threshold_midi: int = TREBLE_8VB_THRESHOLD,
    instrument_name: str = "",
    min_measures: int = OTTAVA_MIN_MEASURES,
) -> music21.stream.Score:
    """为极端音域段落添加 8va/8vb 标记 / Add ottava markings for extreme ranges.

    扫描每个小节:
    - 如果超过 50% 的音符高于 high_threshold → 添加 8va spanner
    - 如果超过 50% 的音符低于 low_threshold → 添加 8vb spanner
    - 需要连续 ≥ min_measures 个小节才添加 (避免孤立标记)
    - bass/guitar 等已有八度谱号的乐器不额外加 ottava

    Args:
        score: music21 Score 对象 (原地修改 + 返回)
        high_threshold_midi: 触发 8va 的最低 MIDI 音高 (默认 G5=79)
        low_threshold_midi: 触发 8vb 的最高 MIDI 音高 (默认 C3=48)
        instrument_name: 乐器名称 (bass/guitar 自动跳过)
        min_measures: 最少连续小节数

    Returns:
        修改后的 Score
    """
    # bass/guitar 已有八度谱号，不再加 ottava
    skip_instruments = {"bass", "guitar"}
    if instrument_name.lower() in skip_instruments:
        return score

    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            continue

        # 逐小节分析
        high_measures: set[int] = set()
        low_measures: set[int] = set()

        for m_idx, measure in enumerate(measures):
            pitches = _get_measure_pitches(measure)
            if not pitches:
                continue

            high_count = sum(1 for p in pitches if p > high_threshold_midi)
            low_count = sum(1 for p in pitches if p < low_threshold_midi)
            total = len(pitches)

            if high_count / total > 0.5:
                high_measures.add(m_idx)
            if low_count / total > 0.5:
                low_measures.add(m_idx)

        # 找连续区域
        _insert_ottava_spanners(part, measures, high_measures, '8va', min_measures)
        _insert_ottava_spanners(part, measures, low_measures, '8vb', min_measures)

    return score


# ===== 内部辅助 =====

def _get_measure_pitches(measure: music21.stream.Measure) -> list[int]:
    """提取一个小节中的所有 MIDI 音高 / Extract all MIDI pitches from a measure.

    Args:
        measure: music21 Measure 对象

    Returns:
        MIDI pitch 列表
    """
    pitches: list[int] = []
    for n in measure.recurse().notes:
        if hasattr(n, 'pitch'):
            pitches.append(n.pitch.midi)
        elif hasattr(n, 'pitches'):
            # Chord: 取最高音
            pitches.extend(p.midi for p in n.pitches)
    return pitches


def _insert_ottava_spanners(
    part: music21.stream.Part,
    measures: list[music21.stream.Measure],
    target_measures: set[int],
    ottava_type: str,
    min_measures: int,
) -> None:
    """在连续区域插入 ottava spanner / Insert ottava spanners for contiguous regions.

    Args:
        part: music21 Part 对象
        measures: 所有小节列表
        target_measures: 需要标记的小节 index 集合
        ottava_type: '8va' 或 '8vb'
        min_measures: 最少连续小节数
    """
    if not target_measures:
        return

    # 找连续区域
    sorted_indices = sorted(target_measures)
    regions: list[list[int]] = []
    current_region = [sorted_indices[0]]

    for idx in sorted_indices[1:]:
        if idx == current_region[-1] + 1:
            current_region.append(idx)
        else:
            if len(current_region) >= min_measures:
                regions.append(current_region)
            current_region = [idx]

    if len(current_region) >= min_measures:
        regions.append(current_region)

    # 为每个连续区域插入 spanner
    for region in regions:
        first_measure = measures[region[0]]
        last_measure = measures[region[-1]]

        try:
            # 创建 ottava spanner
            ottava = spanner.Ottava(type=ottava_type)
            # 找到第一个和最后一个音符
            first_notes = list(first_measure.recurse().notes)
            last_notes = list(last_measure.recurse().notes)

            if first_notes and last_notes:
                ottava.addSpannedElements([first_notes[0], last_notes[-1]])
                part.insert(first_measure.offset, ottava)
        except Exception:
            # 如果 spanner 插入失败，降级为在 LilyPond 层面处理
            pass
