"""节奏分析器测试 / Tests for rhythm_analyzer.py.

测试覆盖:
- RhythmReport: 默认值, summary()
- extract_rhythmic_patterns: 节奏型指纹提取
- flag_spurious_notes: 碎音标记逻辑
- merge_flagged_notes: 碎音合并/移除
- section_review: 分段复核警告
- 内部辅助: _find_beat, _distance_to_nearest_beat
"""

import math
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import numpy as np
    import pretty_midi
    HAS_PRETTY_MIDI = True
except ImportError:
    HAS_PRETTY_MIDI = False
    pretty_midi = None

from src.core.analysis.beat_detector import AnalysisResult
from src.core.analysis.rhythm_analyzer import (
    RhythmReport,
    extract_rhythmic_patterns,
    flag_spurious_notes,
    merge_flagged_notes,
    section_review,
    _find_beat,
    _distance_to_nearest_beat,
    ALIGNMENT_WARNING_PCT,
    DEFAULT_MIN_OCCURRENCES,
    DEFAULT_SHORT_THRESHOLD_MS,
    DEFAULT_REVIEW_INTERVAL,
)


# ===== 辅助 =====

def _make_midi(notes_list, tempo=120):
    """创建测试 MIDI 对象."""
    if not HAS_PRETTY_MIDI:
        return None
    midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    instr = pretty_midi.Instrument(program=0)
    for args in notes_list:
        if len(args) == 4:
            start, end, pitch, vel = args
        elif len(args) == 3:
            start, end, pitch = args
            vel = 90
        else:
            start, end = args
            pitch, vel = 60, 90
        instr.notes.append(pretty_midi.Note(
            velocity=vel, pitch=pitch, start=start, end=end,
        ))
    midi.instruments.append(instr)
    return midi


def _make_analysis(bpm=120.0, beat_times=None, downbeat_times=None,
                   beat_positions=None, time_signature=(4, 4)):
    """创建测试用 AnalysisResult."""
    if beat_times is None:
        # 生成 4 小节 4/4 的 beat grid
        beat_interval = 60.0 / bpm
        beat_times = [i * beat_interval for i in range(16)]
    if beat_positions is None:
        beat_positions = [(i % time_signature[0]) + 1 for i in range(len(beat_times))]
    if downbeat_times is None:
        downbeat_times = [
            beat_times[i] for i, p in enumerate(beat_positions) if p == 1
        ]
    return AnalysisResult(
        bpm=bpm,
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        time_signature=time_signature,
        beat_positions=beat_positions,
    )


# ===== RhythmReport 测试 =====

class TestRhythmReport(unittest.TestCase):
    """RhythmReport 数据类测试."""

    def test_default_values(self):
        r = RhythmReport()
        self.assertEqual(r.total_patterns, 0)
        self.assertEqual(r.rare_pattern_count, 0)
        self.assertEqual(r.flagged_notes, 0)
        self.assertEqual(r.merged_notes, 0)
        self.assertEqual(r.section_warnings, [])
        self.assertEqual(r.pattern_counts, {})

    def test_summary_empty(self):
        """空报告的 summary."""
        r = RhythmReport()
        s = r.summary()
        self.assertIn("节奏型总数", s)
        self.assertIn("0", s)

    def test_summary_with_data(self):
        """有数据时的 summary."""
        r = RhythmReport(
            total_patterns=10,
            rare_pattern_count=3,
            flagged_notes=5,
            merged_notes=4,
            section_warnings=["第 1-16 小节: 偏离"],
        )
        s = r.summary()
        self.assertIn("10", s)
        self.assertIn("3", s)
        self.assertIn("5", s)
        self.assertIn("第 1-16 小节", s)


# ===== _find_beat 测试 =====

class TestFindBeat(unittest.TestCase):
    """_find_beat 辅助函数测试."""

    def test_within_beat_range(self):
        """音符落在两个 beat 之间."""
        beats = [0.0, 0.5, 1.0, 1.5, 2.0]
        self.assertEqual(_find_beat(0.2, beats), 0)   # 在 beat 0 和 1 之间
        self.assertEqual(_find_beat(0.7, beats), 1)   # 在 beat 1 和 2 之间
        self.assertEqual(_find_beat(1.2, beats), 2)   # 在 beat 2 和 3 之间

    def test_exact_beat_boundary(self):
        """音符刚好在 beat 边界."""
        beats = [0.0, 0.5, 1.0]
        self.assertEqual(_find_beat(0.0, beats), 0)   # 在第一个 beat 开始

    def test_after_last_beat(self):
        """音符在最后一个 beat 之后."""
        beats = [0.0, 0.5, 1.0]
        self.assertEqual(_find_beat(2.0, beats), 2)  # 最后一个 beat index

    def test_before_first_beat(self):
        """音符在第一个 beat 之前."""
        beats = [0.5, 1.0]
        self.assertEqual(_find_beat(0.0, beats), -1)

    def test_empty_beats(self):
        """空的 beat list."""
        self.assertEqual(_find_beat(0.0, []), -1)


# ===== _distance_to_nearest_beat 测试 =====

class TestDistanceToNearestBeat(unittest.TestCase):
    """_distance_to_nearest_beat 测试."""

    def test_exact_match(self):
        """音符刚好在 beat 上."""
        beats = [0.0, 0.5, 1.0]
        self.assertEqual(_distance_to_nearest_beat(0.0, beats), 0.0)
        self.assertEqual(_distance_to_nearest_beat(0.5, beats), 0.0)

    def test_between_beats(self):
        """音符在两个 beat 之间."""
        beats = [0.0, 0.5, 1.0]
        self.assertEqual(_distance_to_nearest_beat(0.2, beats), 0.2)  # 距 0.0=0.2, 距 0.5=0.3
        self.assertEqual(_distance_to_nearest_beat(0.7, beats), 0.2)  # 距 0.5=0.2, 距 1.0=0.3

    def test_before_first_beat(self):
        """音符在第一个 beat 之前."""
        beats = [0.5, 1.0]
        self.assertEqual(_distance_to_nearest_beat(0.0, beats), 0.5)

    def test_after_last_beat(self):
        """音符在最后一个 beat 之后."""
        beats = [0.0, 0.5]
        self.assertEqual(_distance_to_nearest_beat(1.0, beats), 0.5)

    def test_empty_beats(self):
        """空的 beat list 返回无穷大."""
        self.assertEqual(_distance_to_nearest_beat(0.0, []), float('inf'))


# ===== extract_rhythmic_patterns 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestExtractRhythmicPatterns(unittest.TestCase):
    """extract_rhythmic_patterns 测试."""

    def test_returns_dict(self):
        """返回值为字典."""
        midi = _make_midi([(0, 0.25, 60)])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        self.assertIsInstance(patterns, dict)

    def test_empty_midi(self):
        """空 MIDI 返回空字典."""
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        self.assertEqual(patterns, {})

    def test_raises_on_empty_beats(self):
        """空 beat_times 抛出 ValueError."""
        midi = _make_midi([(0, 0.25, 60)])
        analysis = AnalysisResult(bpm=120.0)  # 无 beat_times
        with self.assertRaises(ValueError):
            extract_rhythmic_patterns(midi, analysis)

    def test_pattern_keys_are_strings(self):
        """pattern 的 key 都是字符串."""
        # 在 120 BPM, 4/4 下生成一些音符
        midi = _make_midi([
            (0.0, 0.25, 60),          # beat 0, pos 0
            (0.5, 0.75, 62),          # beat 1, pos 0
            (1.0, 1.25, 64),          # beat 2, pos 0
            (0.0, 0.125, 67),         # beat 0, pos 0 (重叠)
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        for key in patterns:
            self.assertIsInstance(key, str)
            # key 格式: "b{beat_position}:{grid_position}"
            self.assertIn("b", key)
            self.assertIn(":", key)

    def test_notes_grouped_by_grid_position(self):
        """同一 grid 位置的音符归入同一 pattern."""
        midi = _make_midi([
            (0.0, 0.25, 60),
            (0.0, 0.25, 64),   # 同一 onset
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        # 两个音符在同一个 onset → 同一个 pattern key
        note_indices = []
        for indices in patterns.values():
            note_indices.extend(indices)
        self.assertEqual(len(note_indices), 2)  # 两个都被分配到 pattern


# ===== flag_spurious_notes 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestFlagSpuriousNotes(unittest.TestCase):
    """flag_spurious_notes 测试."""

    def test_no_patterns_returns_empty(self):
        """无 pattern 时返回空列表."""
        midi = _make_midi([(0, 0.25, 60)])
        flagged = flag_spurious_notes(midi, {})
        self.assertEqual(flagged, [])

    def test_common_pattern_not_flagged(self):
        """出现多次的 pattern 不被标记."""
        midi = _make_midi([
            (0.0, 0.25, 60),   # quarter note on beat 1
            (1.0, 1.25, 62),   # quarter note on beat 3 (same pattern pos)
            (2.0, 2.25, 64),   # quarter note on beat 1 (bar 2)
            (3.0, 3.25, 65),   # quarter note on beat 3 (bar 2)
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        flagged = flag_spurious_notes(midi, patterns, analysis=analysis,
                                       min_occurrences=2)
        self.assertEqual(len(flagged), 0)  # 所有 pattern 至少出现 2 次

    def test_short_threshold_respected(self):
        """长于阈值的音符不标记 (即使稀有)."""
        # 一个出现一次但时值很长的音符 → 不标记
        midi = _make_midi([
            (0.0, 2.0, 60),  # 半音符, 远长于 150ms
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        flagged = flag_spurious_notes(midi, patterns, analysis=analysis,
                                       min_occurrences=2,
                                       short_note_threshold_ms=150.0)
        self.assertEqual(len(flagged), 0)

    def test_rare_short_note_flagged(self):
        """出现一次且很短的音符被标记."""
        midi = _make_midi([
            (0.0, 0.05, 60),   # 50ms — 很短且只出现一次
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        flagged = flag_spurious_notes(midi, patterns, analysis=analysis,
                                       min_occurrences=2,
                                       short_note_threshold_ms=150.0)
        self.assertEqual(len(flagged), 1)

    def test_returns_sorted_indices(self):
        """返回的索引已排序."""
        midi = _make_midi([
            (0.0, 0.05, 60),   # note 0 — 稀有短音
            (2.0, 2.05, 64),   # note 1 — 稀有短音
        ])
        analysis = _make_analysis(bpm=120.0)
        patterns = extract_rhythmic_patterns(midi, analysis)
        flagged = flag_spurious_notes(midi, patterns, analysis=analysis,
                                       min_occurrences=2)
        self.assertEqual(flagged, sorted(flagged))


# ===== merge_flagged_notes 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestMergeFlaggedNotes(unittest.TestCase):
    """merge_flagged_notes 测试."""

    def test_empty_flagged_no_change(self):
        """空标记列表时 MIDI 不变."""
        midi = _make_midi([(0, 0.5, 60)])
        original_count = len(midi.instruments[0].notes)
        result = merge_flagged_notes(midi, [])
        self.assertEqual(len(result.instruments[0].notes), original_count)

    def test_flagged_note_removed_if_no_neighbor(self):
        """孤立标记音符直接移除."""
        midi = _make_midi([
            (0.0, 0.05, 60),  # 标记
            (2.0, 2.5, 64),   # 太远, 不是 neighbor
        ])
        result = merge_flagged_notes(midi, [0])
        # 标记音符被移除 (没有足够近的同音高 neighbor)
        notes_after = result.instruments[0].notes
        self.assertEqual(len(notes_after), 1)

    def test_flagged_note_merged_with_neighbor(self):
        """标记音符延长相邻同音高音符."""
        midi = _make_midi([
            (0.0, 0.5, 60),   # note 0 — neighbor
            (0.51, 0.55, 60), # note 1 — 标记 (同音高, 相邻)
        ])
        result = merge_flagged_notes(midi, [1], analysis=_make_analysis(bpm=120.0))
        notes = result.instruments[0].notes
        # note 0 的 end 应延长到覆盖 note 1
        self.assertGreaterEqual(notes[0].end, 0.55)

    def test_different_pitch_not_merged(self):
        """不同音高音符不作为 neighbor."""
        midi = _make_midi([
            (0.0, 0.5, 60),   # C4
            (0.51, 0.55, 72), # C5 — 标记 (不同音高)
        ])
        result = merge_flagged_notes(midi, [1], analysis=_make_analysis(bpm=120.0))
        # note 1 应该被移除 (无同音高 neighbor)
        notes = result.instruments[0].notes
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].pitch, 60)


# ===== section_review 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestSectionReview(unittest.TestCase):
    """section_review 测试."""

    def test_empty_midi_no_warnings(self):
        """空 MIDI 无警告."""
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        analysis = _make_analysis(bpm=120.0)
        warnings = section_review(midi, analysis)
        self.assertEqual(warnings, [])

    def test_no_downbeats_no_warnings(self):
        """无 downbeat 数据时返回空."""
        midi = _make_midi([(0, 0.5, 60)])
        analysis = AnalysisResult(bpm=120.0)  # 无 downbeat_times
        warnings = section_review(midi, analysis)
        self.assertEqual(warnings, [])

    def test_perfectly_aligned_notes_no_warning(self):
        """拍位对齐的音符不产生警告."""
        # 所有 note onset 精确在 beat 时间上
        midi = _make_midi([
            (0.0, 0.25, 60),
            (0.5, 0.75, 62),
            (1.0, 1.25, 64),
            (1.5, 1.75, 65),
        ])
        analysis = _make_analysis(bpm=120.0)
        warnings = section_review(midi, analysis, warning_threshold=0.3)
        # 所有音符精确对齐 → 无警告
        self.assertEqual(warnings, [])

    def test_off_grid_notes_generate_warning(self):
        """偏离拍位的音符产生警告."""
        # 大部分音符偏移 (off-grid)
        midi = _make_midi([
            (0.05, 0.3, 60),   # offset=0.05 (off-grid)
            (0.55, 0.8, 62),   # offset=0.55 (off-grid)
            (1.05, 1.3, 64),   # offset=1.05 (off-grid)
            (1.55, 1.8, 65),   # offset=1.55 (off-grid)
        ])
        analysis = _make_analysis(bpm=120.0)
        warnings = section_review(midi, analysis, warning_threshold=0.1)
        self.assertGreater(len(warnings), 0)

    def test_warning_format(self):
        """警告信息包含小节号和偏离比例."""
        midi = _make_midi([
            (0.1, 0.3, 60),    # off-grid
            (0.6, 0.8, 62),    # off-grid
            (1.1, 1.3, 64),    # off-grid
            (1.6, 1.8, 65),    # off-grid
        ])
        analysis = _make_analysis(bpm=120.0)
        warnings = section_review(midi, analysis, warning_threshold=0.05)
        for w in warnings:
            self.assertTrue("小节" in w)
            self.assertTrue("%" in w or "复核" in w)


# ===== 常量验证 =====

class TestConstants(unittest.TestCase):
    """常量合理性验证."""

    def test_alignment_warning_pct_in_range(self):
        """拍位对齐警告阈值在合理范围."""
        self.assertTrue(0.0 < ALIGNMENT_WARNING_PCT < 1.0)

    def test_short_threshold_positive(self):
        """碎音阈值为正."""
        self.assertGreater(DEFAULT_SHORT_THRESHOLD_MS, 0)

    def test_min_occurrences_positive(self):
        """最小出现次数为正."""
        self.assertGreaterEqual(DEFAULT_MIN_OCCURRENCES, 1)

    def test_review_interval_positive(self):
        """分段复核间隔为正."""
        self.assertGreater(DEFAULT_REVIEW_INTERVAL, 0)


if __name__ == '__main__':
    unittest.main()
