"""谱号与八度优化测试 / Tests for octave_optimizer.py.

测试覆盖:
- get_instrument_clef: 每种乐器的默认谱号
- optimize_clef_for_instrument: 谱号替换/插入
- apply_ottava: 极端音域 8va/8vb 标记
- 辅助函数: _get_measure_pitches, _insert_ottava_spanners
- 阈值常量合理性
"""

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import music21
    from music21 import stream, note, chord, clef, meter, tempo
    HAS_MUSIC21 = True
except ImportError:
    HAS_MUSIC21 = False

from src.core.notation.octave_optimizer import (
    get_instrument_clef,
    optimize_clef_for_instrument,
    apply_ottava,
    _get_measure_pitches,
    _insert_ottava_spanners,
    BASS_8_MEAN_PITCH,
    TREBLE_8VA_THRESHOLD,
    TREBLE_8VB_THRESHOLD,
    OTTAVA_MIN_MEASURES,
    INSTRUMENT_CLEF_MAP,
)


# ===== 辅助 =====

def _make_simple_score(measures_data=None):
    """创建测试用 music21 Score.

    Args:
        measures_data: [(pitch_list, quarter_lengths), ...] 每小节的音符数据
                       如果为 None, 返回一个空 Score
    """
    s = stream.Score()
    part = stream.Part()
    s.insert(0, part)

    if measures_data:
        for note_pitches, qls in measures_data:
            m = stream.Measure()
            m.append(meter.TimeSignature('4/4'))
            for i, (p, ql) in enumerate(zip(note_pitches, qls)):
                if isinstance(p, int):
                    n = note.Note(p)
                else:
                    n = note.Note(p[0] if isinstance(p, tuple) else p)
                n.quarterLength = ql
                m.append(n)
            part.append(m)

    return s


# ===== get_instrument_clef 测试 =====

@unittest.skipIf(not HAS_MUSIC21, "music21 未安装")
class TestGetInstrumentClef(unittest.TestCase):
    """get_instrument_clef 测试."""

    def test_bass_clef(self):
        """bass → Bass8vbClef."""
        c = get_instrument_clef("bass")
        self.assertIsInstance(c, clef.Bass8vbClef)

    def test_guitar_clef(self):
        """guitar → Treble8vbClef."""
        c = get_instrument_clef("guitar")
        self.assertIsInstance(c, clef.Treble8vbClef)

    def test_piano_clef(self):
        """piano → TrebleClef."""
        c = get_instrument_clef("piano")
        self.assertIsInstance(c, clef.TrebleClef)

    def test_vocals_clef(self):
        """vocals → TrebleClef."""
        c = get_instrument_clef("vocals")
        self.assertIsInstance(c, clef.TrebleClef)

    def test_unknown_clef(self):
        """未知乐器 → TrebleClef (fallback)."""
        c = get_instrument_clef("saxophone")
        self.assertIsInstance(c, clef.TrebleClef)

    def test_case_insensitive(self):
        """乐器名不区分大小写."""
        c_lower = get_instrument_clef("bass")
        c_upper = get_instrument_clef("BASS")
        c_mixed = get_instrument_clef("BaSs")
        self.assertEqual(type(c_lower), type(c_upper))
        self.assertEqual(type(c_lower), type(c_mixed))


# ===== optimize_clef_for_instrument 测试 =====

@unittest.skipIf(not HAS_MUSIC21, "music21 未安装")
class TestOptimizeClefForInstrument(unittest.TestCase):
    """optimize_clef_for_instrument 测试."""

    def test_bass_gets_bass8_clef(self):
        """bass 的 Part 被赋予 Bass8vbClef."""
        score = _make_simple_score([([60, 62, 64], [1.0, 1.0, 2.0])])
        score = optimize_clef_for_instrument(score, "bass")

        # 检查 Part 中插入了谱号
        part = score.parts[0]
        clefs = [el for el in part.recurse() if isinstance(el, clef.Clef)]
        self.assertGreater(len(clefs), 0)
        self.assertIsInstance(clefs[0], clef.Bass8vbClef)

    def test_guitar_gets_treble8_clef(self):
        """guitar 的 Part 被赋予 Treble8vbClef."""
        score = _make_simple_score([([64, 67, 71], [1.0, 1.0, 2.0])])
        score = optimize_clef_for_instrument(score, "guitar")

        part = score.parts[0]
        clefs = [el for el in part.recurse() if isinstance(el, clef.Clef)]
        self.assertGreater(len(clefs), 0)
        self.assertIsInstance(clefs[0], clef.Treble8vbClef)

    def test_piano_gets_treble_clef(self):
        """piano 的 Part 被赋予 TrebleClef."""
        score = _make_simple_score([([60, 64, 67], [1.0, 1.0, 2.0])])
        score = optimize_clef_for_instrument(score, "piano")

        part = score.parts[0]
        clefs = [el for el in part.recurse() if isinstance(el, clef.Clef)]
        self.assertGreater(len(clefs), 0)
        self.assertIsInstance(clefs[0], clef.TrebleClef)

    def test_existing_clef_replaced(self):
        """已有谱号时只替换, 不新增."""
        score = _make_simple_score([([60, 62], [1.0, 1.0])])
        # 手动插入一个假谱号
        part = score.parts[0]
        part.insert(0, clef.BassClef())

        score = optimize_clef_for_instrument(score, "bass")

        clefs = [el for el in part.recurse() if isinstance(el, clef.Clef)]
        self.assertEqual(len(clefs), 1)  # 只应有一个
        self.assertIsInstance(clefs[0], clef.Bass8vbClef)  # 已被替换

    def test_multi_part_score(self):
        """多 Part Score 每个 Part 都优化."""
        score = stream.Score()
        part1 = stream.Part()
        part2 = stream.Part()
        part1.append(note.Note(60))
        part2.append(note.Note(48))
        score.insert(0, part1)
        score.insert(0, part2)

        score = optimize_clef_for_instrument(score, "bass")

        for part in score.parts:
            clefs = [el for el in part.recurse() if isinstance(el, clef.Clef)]
            self.assertGreater(len(clefs), 0)
            self.assertIsInstance(clefs[0], clef.Bass8vbClef)


# ===== apply_ottava 测试 =====

@unittest.skipIf(not HAS_MUSIC21, "music21 未安装")
class TestApplyOttava(unittest.TestCase):
    """apply_ottava 测试."""

    def test_bass_skipped(self):
        """bass 已有八度谱号, 自动跳过 ottava."""
        score = _make_simple_score([
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),  # 高音 → 理应触发 8va
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),
        ])
        score = apply_ottava(score, instrument_name="bass")

        # bass 应该跳过 — ottava spanners 不会被插入
        part = score.parts[0]
        from music21 import spanner
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 0)

    def test_guitar_skipped(self):
        """guitar 也跳过 ottava."""
        score = _make_simple_score([
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),
            ([84, 85, 86, 84], [1.0, 1.0, 1.0, 1.0]),
        ])
        score = apply_ottava(score, instrument_name="guitar")

        from music21 import spanner
        part = score.parts[0]
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 0)

    def test_piano_high_notes_trigger_8va(self):
        """piano 极端高音触发 8va (连续 ≥ N 小节)."""
        # 创建多小节全部高音 → 应触发 8va
        high_pitches = [84, 86, 88, 84]  # all > 79 (G5)
        measures_data = [(high_pitches, [1.0] * 4) for _ in range(5)]

        score = _make_simple_score(measures_data)
        # 先给各小节编号, 确保 measure 数量足够
        score = apply_ottava(
            score,
            high_threshold_midi=TREBLE_8VA_THRESHOLD,
            instrument_name="piano",
            min_measures=2,
        )

        # 检查是否有 ottava 被插入
        from music21 import spanner
        part = score.parts[0]
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertGreater(len(ottavas), 0)

    def test_low_notes_trigger_8vb(self):
        """piano 极端低音触发 8vb (连续 ≥ N 小节)."""
        low_pitches = [40, 42, 38, 40]  # all < 48 (C3)
        measures_data = [(low_pitches, [1.0] * 4) for _ in range(5)]

        score = _make_simple_score(measures_data)
        score = apply_ottava(
            score,
            low_threshold_midi=TREBLE_8VB_THRESHOLD,
            instrument_name="piano",
            min_measures=2,
        )

        from music21 import spanner
        part = score.parts[0]
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertGreater(len(ottavas), 0)

    def test_single_measure_not_triggered(self):
        """只有一小节极端音域 → 不触发 ottava (少于 min_measures)."""
        # 仅 1 小节高音
        score = _make_simple_score([
            ([84, 86, 88, 84], [1.0, 1.0, 1.0, 1.0]),
            ([60, 62, 64, 60], [1.0, 1.0, 1.0, 1.0]),  # 正常音域
        ])
        score = apply_ottava(
            score,
            high_threshold_midi=TREBLE_8VA_THRESHOLD,
            instrument_name="piano",
            min_measures=2,
        )

        from music21 import spanner
        part = score.parts[0]
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 0)

    def test_empty_score(self):
        """空 Score 不崩溃."""
        score = stream.Score()
        part = stream.Part()
        score.insert(0, part)
        result = apply_ottava(score, instrument_name="piano")
        self.assertIsNotNone(result)


# ===== _get_measure_pitches 测试 =====

@unittest.skipIf(not HAS_MUSIC21, "music21 未安装")
class TestGetMeasurePitches(unittest.TestCase):
    """_get_measure_pitches 辅助函数测试."""

    def test_single_notes(self):
        """单音小节."""
        m = stream.Measure()
        m.append(note.Note(60))
        m.append(note.Note(64))
        m.append(note.Note(67))

        pitches = _get_measure_pitches(m)
        self.assertEqual(pitches, [60, 64, 67])

    def test_with_chords(self):
        """和弦小节的音高提取."""
        m = stream.Measure()
        m.append(note.Note(60))
        c = chord.Chord([64, 67, 72])
        m.append(c)

        pitches = _get_measure_pitches(m)
        self.assertIn(60, pitches)
        self.assertIn(64, pitches)
        self.assertIn(67, pitches)
        self.assertIn(72, pitches)

    def test_empty_measure(self):
        """空小节返回空列表."""
        m = stream.Measure()
        pitches = _get_measure_pitches(m)
        self.assertEqual(pitches, [])

    def test_with_rests(self):
        """含休止符小节跳过休止符."""
        m = stream.Measure()
        m.append(note.Note(60))
        m.append(note.Rest())
        m.append(note.Note(64))

        pitches = _get_measure_pitches(m)
        self.assertEqual(pitches, [60, 64])


# ===== _insert_ottava_spanners 测试 =====

@unittest.skipIf(not HAS_MUSIC21, "music21 未安装")
class TestInsertOttavaSpanners(unittest.TestCase):
    """_insert_ottava_spanners 辅助函数测试."""

    def test_empty_target_set(self):
        """空目标集合不插入 spanner."""
        measures = [stream.Measure() for _ in range(4)]
        part = stream.Part()
        for m in measures:
            part.append(m)
            m.append(note.Note(60))

        _insert_ottava_spanners(part, measures, set(), "8va", min_measures=2)

        from music21 import spanner
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 0)

    def test_contiguous_region_gets_single_spanner(self):
        """连续区域 → 一个 spanner 覆盖整个区域."""
        measures = []
        part = stream.Part()
        for _ in range(4):
            m = stream.Measure()
            m.append(note.Note(60))
            measures.append(m)
            part.append(m)

        # 连续: 小节 0, 1, 2
        _insert_ottava_spanners(
            part, measures, {0, 1, 2}, "8va", min_measures=2,
        )

        from music21 import spanner
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 1)  # 一个 spanner

    def test_non_contiguous_regions(self):
        """非连续区域 → 每个连续区域一个 spanner."""
        measures = []
        part = stream.Part()
        for _ in range(6):
            m = stream.Measure()
            m.append(note.Note(60))
            measures.append(m)
            part.append(m)

        # 两个不连续区域: {0, 1} 和 {3, 4, 5}
        _insert_ottava_spanners(
            part, measures, {0, 1, 3, 4, 5}, "8va", min_measures=2,
        )

        from music21 import spanner
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 2)

    def test_region_below_min_measures(self):
        """区域小于 min_measures → 不插入."""
        measures = []
        part = stream.Part()
        for _ in range(3):
            m = stream.Measure()
            m.append(note.Note(60))
            measures.append(m)
            part.append(m)

        # 只有 1 个小节
        _insert_ottava_spanners(
            part, measures, {0}, "8va", min_measures=2,
        )

        from music21 import spanner
        ottavas = [el for el in part.recurse() if isinstance(el, spanner.Ottava)]
        self.assertEqual(len(ottavas), 0)


# ===== 常量验证 =====

class TestConstants(unittest.TestCase):
    """常量合理性验证 (纯 Python, 无需 music21)."""

    def test_clef_map_has_expected_entries(self):
        """INSTRUMENT_CLEF_MAP 包含预期乐器."""
        self.assertIn("bass", INSTRUMENT_CLEF_MAP)
        self.assertIn("guitar", INSTRUMENT_CLEF_MAP)
        self.assertIn("piano", INSTRUMENT_CLEF_MAP)
        self.assertIn("vocals", INSTRUMENT_CLEF_MAP)

    def test_bass8_threshold_reasonable(self):
        """BASS_8_MEAN_PITCH 在合理范围 (B2~F3)."""
        self.assertTrue(35 < BASS_8_MEAN_PITCH < 65)

    def test_ottava_thresholds_reasonable(self):
        """8va 阈值 > 8vb 阈值."""
        self.assertGreater(TREBLE_8VA_THRESHOLD, TREBLE_8VB_THRESHOLD)

    def test_ottava_min_measures_positive(self):
        """Ottava 最小连续小节数 > 0."""
        self.assertGreater(OTTAVA_MIN_MEASURES, 0)


if __name__ == '__main__':
    unittest.main()
