"""MIDI → music21 Score 转换器 / MIDI to music21 Score converter.

将 MIDI 文件（或 pretty_midi 对象）转换为 music21 Score，
自动检测调性、拍号、速度，并进行量化清洗。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import music21
from music21 import converter, instrument, key, meter, tempo, stream, note, chord

logger = logging.getLogger(__name__)


def midi_to_score(
    midi_path: Path | str,
    quantize: bool = True,
    quantize_denominator: int = 16,  # 量化到 1/16 音符 (16分音符)
    remove_overlaps: bool = True,
    simplify_durations: bool = True,
    instrument_name: str = "",
    analysis: Optional[object] = None,  # AnalysisResult (避免循环导入)
    progress_callback: Callable[[int, str], None] | None = None,
) -> music21.stream.Score:
    """将 MIDI 文件转换为 music21 Score / Convert MIDI file to music21 Score.

    Args:
        midi_path: MIDI 文件路径
        quantize: 是否量化音符时值
        quantize_denominator: 量化精度 (4=四分音符, 8=八分, 16=十六分, 默认16)
        remove_overlaps: 是否移除同音高音符重叠
        simplify_durations: 是否简化时值表示 (三连音→附点等)
        instrument_name: 乐器名称 (用于谱号优化, 如 'bass', 'guitar')
        analysis: 节拍分析结果 (BeatDetector 输出), 用于强拍对齐
        progress_callback: 进度回调 (percent, message)

    Returns:
        music21 Score 对象 (已拆分为多个 Part, 谱号已优化, 小节已对齐)

    Raises:
        FileNotFoundError: MIDI 文件不存在
        ValueError: MIDI 文件解析失败
    """
    midi_path = Path(midi_path)
    if not midi_path.exists():
        raise FileNotFoundError(f"MIDI 文件不存在: {midi_path}")

    if progress_callback:
        progress_callback(5, "解析 MIDI 文件...")

    # 解析 MIDI
    try:
        score = converter.parse(str(midi_path))
    except Exception as e:
        raise ValueError(f"MIDI 解析失败: {e}") from e

    if progress_callback:
        progress_callback(20, "拆分声部...")

    # 确保是 Score 对象
    if not isinstance(score, stream.Score):
        # 如果是单个 Part，包裹成 Score
        s = stream.Score()
        s.insert(0, score)
        score = s

    # 展开重复和跳转
    score = score.expandRepeats()

    # 强拍对齐 (如果提供了 analysis)
    if analysis is not None:
        if progress_callback:
            progress_callback(35, "对齐强拍...")
        score = _align_measures_to_downbeats(score, analysis)

    # 量化
    if quantize:
        if progress_callback:
            progress_callback(40, f"量化到 1/{quantize_denominator} 音符...")
        score = _quantize_score(score, denominator=quantize_denominator)

    # 处理重叠
    if remove_overlaps:
        if progress_callback:
            progress_callback(55, "移除重叠音符...")
        score = _remove_overlaps(score)

    # 简化时值
    if simplify_durations:
        if progress_callback:
            progress_callback(70, "简化时值表示...")
        score = _simplify_durations(score)

    # 检测并添加调号
    if progress_callback:
        progress_callback(80, "检测调性/拍号...")
    score = _analyze_and_annotate(score)

    # 谱号优化 (根据乐器选择最佳谱号)
    if instrument_name:
        if progress_callback:
            progress_callback(90, f"优化 {instrument_name} 谱号...")
        try:
            from src.core.notation.octave_optimizer import optimize_clef_for_instrument
            score = optimize_clef_for_instrument(score, instrument_name)
        except ImportError:
            pass  # 可选模块，不阻断流程

    if progress_callback:
        progress_callback(100, "Score 转换完成")

    return score


def split_midi_parts(
    score: music21.stream.Score,
) -> list[music21.stream.Part]:
    """将 Score 拆分为独立声部 / Split Score into individual Parts.

    如果是单轨 MIDI (只有一个 Part)，尝试按音域分离旋律/伴奏。

    Args:
        score: music21 Score 对象

    Returns:
        Part 对象列表
    """
    parts = list(score.parts)

    # 如果只有一个 part (单轨 MIDI)，尝试按音域分离
    if len(parts) == 1:
        single = parts[0]
        # 尝试按通道分离
        channels = set()
        for n in single.recurse().notes:
            if hasattr(n, 'midi') and hasattr(n.midi, 'channel'):
                channels.add(n.midi.channel)

        if len(channels) > 1:
            # 有多种通道 → 按通道分离
            separated = {}
            for ch in channels:
                part = stream.Part()
                for n in single.recurse().notesAndRests:
                    ch_val = getattr(getattr(n, 'midi', None), 'channel', None)
                    if ch_val == ch:
                        part.append(n)
                if len(part.notes) > 0:
                    separated[f"channel_{ch}"] = part
            if len(separated) > 1:
                return list(separated.values())

    return parts


def detect_key_and_tempo(
    score: music21.stream.Score,
) -> dict:
    """检测 MIDI 的调性和速度 / Detect key and tempo from MIDI score.

    Args:
        score: music21 Score 对象

    Returns:
        {
            'key': music21.key.Key | None,      # 检测到的调性
            'key_name': str,                      # 调性名称 (如 'C major')
            'key_confidence': float,              # 置信度 0-1
            'tempo_bpm': float | None,            # 平均速度 BPM
            'time_signature': str | None,         # 拍号 (如 '4/4')
        }
    """
    # 调性分析 (Krumhansl-Kessler)
    key_obj = score.analyze('key')

    # BPM
    tempo_bpm = None
    try:
        # 尝试从第一部分获取速度标记
        for el in score.recurse():
            if isinstance(el, tempo.MetronomeMark):
                tempo_bpm = el.number
                break
        # 没有显式速度标记时估算
        if tempo_bpm is None:
            # 检测四分音符时长
            beat_duration = score.secondsMap.get('quarterLength', None)
            if beat_duration:
                # 找最常见的事件间隔
                pass
    except Exception:
        logger.debug("BPM 检测失败 (MIDI 中无 MetronomeMark)", exc_info=True)

    # 拍号
    ts_str = None
    for el in score.recurse():
        if isinstance(el, meter.TimeSignature):
            ts_str = el.ratioString
            break

    return {
        'key': key_obj,
        'key_name': str(key_obj) if key_obj else 'unknown',
        'key_confidence': key_obj.correlationCoefficient if key_obj else 0.0,
        'tempo_bpm': tempo_bpm,
        'time_signature': ts_str or '4/4',
    }


# ===== 内部辅助函数 =====

def _quantize_score(
    score: music21.stream.Score,
    denominator: int = 16,
) -> music21.stream.Score:
    """量化学符时值到指定网格 / Quantize note durations to grid."""
    try:
        score = score.quantize(
            quarterLengthDivisors=(denominator // 4,),  # 4=1beat grid, 8=0.5beat, 16=0.25beat
            processOffsets=True,
            processDurations=True,
        )
    except Exception:
        logger.debug("music21 量化失败 (可能是兼容性问题), 跳过此步骤", exc_info=True)
    return score


def _remove_overlaps(
    score: music21.stream.Score,
) -> music21.stream.Score:
    """移除同音高重叠音符 / Remove overlapping notes of same pitch.

    当同一音高的两个音符重叠时，截断或移除其中一个。
    """
    for part in score.parts:
        for measure in part.getElementsByClass(stream.Measure):
            notes_by_pitch: dict[str, list] = {}
            for n in measure.recurse().notes:
                # Handle both Note and Chord objects (music21 v10+)
                if hasattr(n, 'nameWithOctave'):
                    pitch_key = n.nameWithOctave
                else:
                    # Chord: use sorted pitch names as compound key
                    pitch_key = '|'.join(sorted(p.nameWithOctave for p in n.pitches))
                if pitch_key not in notes_by_pitch:
                    notes_by_pitch[pitch_key] = []
                notes_by_pitch[pitch_key].append(n)

            for pitch_key, note_list in notes_by_pitch.items():
                if len(note_list) < 2:
                    continue
                # 按起始时间排序
                note_list.sort(key=lambda x: x.offset)
                # 检查重叠
                for i in range(len(note_list) - 1):
                    curr = note_list[i]
                    next_n = note_list[i + 1]
                    curr_end = curr.offset + curr.quarterLength
                    if next_n.offset < curr_end:
                        # 截断当前音符
                        curr.quarterLength = max(
                            0.25, next_n.offset - curr.offset
                        )
    return score


def _simplify_durations(
    score: music21.stream.Score,
) -> music21.stream.Score:
    """简化复杂时值表示 / Simplify complex duration notations.

    将极短音符、非标准时值简化为标准时值。
    """
    from fractions import Fraction

    # 标准时值列表 (以 quarterLength 表示)
    standard_durations = [
        4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5,
        0.375, 0.25, 0.1875, 0.125, 0.0625,
    ]

    def snap_duration(ql: float) -> float:
        """将时值吸附到最接近的标准时值."""
        if ql <= 0:
            return 0.25
        best = min(standard_durations, key=lambda d: abs(d - ql))
        # 允许 25% 误差
        if abs(best - ql) / max(ql, 0.001) < 0.25:
            return best
        return ql

    for part in score.parts:
        for n in part.recurse().notes:
            ql = n.quarterLength
            if ql is not None:
                n.quarterLength = snap_duration(float(ql))

    return score


def _analyze_and_annotate(
    score: music21.stream.Score,
) -> music21.stream.Score:
    """检测并标注调号、拍号到 Score / Detect and annotate key/time sig."""
    info = detect_key_and_tempo(score)

    # 确保每个 Part 的开头有调号和拍号
    ts_obj = meter.TimeSignature(info['time_signature'] or '4/4')

    for part in score.parts:
        # 检查是否已有调号
        has_key = any(isinstance(el, key.Key) for el in part.recurse())
        has_ts = any(isinstance(el, meter.TimeSignature) for el in part.recurse())

        if not has_key and info['key']:
            part.insert(0, info['key'])

        if not has_ts:
            part.insert(0, ts_obj)

        # 添加速度标记 (如果没有)
        has_tempo = any(isinstance(el, tempo.MetronomeMark) for el in part.recurse())
        if not has_tempo and info['tempo_bpm']:
            part.insert(0, tempo.MetronomeMark(number=info['tempo_bpm']))

    return score


def _align_measures_to_downbeats(
    score: music21.stream.Score,
    analysis,  # AnalysisResult
) -> music21.stream.Score:
    """对齐小节边界到检测到的强拍 / Align measure boundaries to detected downbeats.

    music21 的 MIDI import 基于 MIDI 文件中的拍号和时间签名创建小节。
    如果原始转录的 BPM 不对 (basic-pitch 通常写入默认 120 BPM),
    小节边界会与实际音频的强拍位置产生漂移。

    修复策略:
    1. 比较 Score 中的速度标记与 BeatDetector 检测到的 BPM
    2. 若偏差 > 3%, 更新 Score 的 MetronomeMark 以匹配检测值
    3. 检查并修正弱起小节 (anacrusis) 偏移

    Args:
        score: music21 Score 对象 (原地修改)
        analysis: 节拍分析结果 (含 bpm 和 downbeat_times)

    Returns:
        修改后的 Score
    """
    if not hasattr(analysis, 'downbeat_times') or not analysis.downbeat_times:
        return score

    detected_bpm = getattr(analysis, 'bpm', None)
    if detected_bpm is None or detected_bpm <= 0:
        return score

    # ---- 步骤 1: BPM 对齐 ----
    # 检查 Score 中的速度标记是否与检测到的 BPM 一致
    score_tempo: Optional[float] = None
    for el in score.recurse():
        if isinstance(el, tempo.MetronomeMark):
            score_tempo = el.number
            break

    bpm_mismatch = (
        score_tempo is not None
        and abs(score_tempo - detected_bpm) / detected_bpm > 0.03
    )

    if bpm_mismatch:
        logger.info(
            "强拍对齐: Score BPM=%.1f → 检测 BPM=%.1f (偏差 %.1f%%)",
            score_tempo, detected_bpm,
            abs(score_tempo - detected_bpm) / detected_bpm * 100,
        )
        # 更新所有 MetronomeMark
        for el in score.recurse():
            if isinstance(el, tempo.MetronomeMark):
                el.number = detected_bpm

    # ---- 步骤 2: 弱起小节 (anacrusis) 处理 ----
    # 如果第一个 downbeat 距时间零点超过半拍, 说明有弱起
    # 调整 measure 内元素的偏移使强拍对齐小节线
    first_downbeat = analysis.downbeat_times[0]
    half_beat = analysis.beat_interval / 2.0

    if first_downbeat > half_beat:
        logger.info(
            "强拍对齐: 检测到弱起小节 (首个 downbeat @ %.2fs), 调整偏移...",
            first_downbeat,
        )
        for part in score.parts:
            for el in part.recurse():
                try:
                    current_offset = float(el.offset)
                    if current_offset >= first_downbeat:
                        el.offset = current_offset - first_downbeat
                except (AttributeError, TypeError):
                    pass

    return score
