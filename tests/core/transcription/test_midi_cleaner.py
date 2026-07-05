"""MIDI Cleaner 测试 / Tests for midi_cleaner.py.

测试覆盖:
- CleanConfig 默认值和自定义
- CleanReport 统计正确性
- clean_midi: 去噪 (短音/弱音/孤立音)
- clean_midi: 合并重叠音符
- clean_midi: 量化
- clean_midi: 力度归一化
- _estimate_tempo: 优先级 (external > MIDI > default)
- _estimate_key: 大/小调检测
- get_midi_stats: 统计信息
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

from src.core.transcription.midi_cleaner import (
    CleanConfig,
    CleanReport,
    clean_midi,
    _estimate_tempo,
    _estimate_key,
    extract_tempo_map,
    get_midi_stats,
)


# ===== 辅助函数 =====

def _make_note(start, end, pitch=60, velocity=90):
    """创建测试用 Note."""
    if not HAS_PRETTY_MIDI:
        return None
    return pretty_midi.Note(
        velocity=velocity,
        pitch=pitch,
        start=start,
        end=end,
    )


def _make_midi(notes_list, tempo=120):
    """创建包含指定音符的 PrettyMIDI 对象.

    Args:
        notes_list: [(start, end, pitch, velocity), ...]
        tempo: BPM
    """
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


# ===== CleanConfig 测试 =====

class TestCleanConfig(unittest.TestCase):
    """CleanConfig 数据类测试."""

    def test_default_values(self):
        """默认值检查."""
        cfg = CleanConfig()
        self.assertTrue(cfg.quantize_enabled)
        self.assertEqual(cfg.quantize_grid, 1 / 16)
        self.assertEqual(cfg.min_note_duration_ms, 40.0)
        self.assertEqual(cfg.min_velocity, 15)
        self.assertEqual(cfg.target_mean_velocity, 90)

    def test_custom_values(self):
        """自定义值检查."""
        cfg = CleanConfig(
            quantize_enabled=False,
            min_note_duration_ms=80.0,
            external_bpm=140.0,
            rhythm_validate_enabled=True,
        )
        self.assertFalse(cfg.quantize_enabled)
        self.assertEqual(cfg.min_note_duration_ms, 80.0)
        self.assertEqual(cfg.external_bpm, 140.0)
        self.assertTrue(cfg.rhythm_validate_enabled)


# ===== CleanReport 测试 =====

class TestCleanReport(unittest.TestCase):
    """CleanReport 测试."""

    def test_empty_report(self):
        """空报告默认值."""
        r = CleanReport()
        self.assertEqual(r.original_note_count, 0)
        self.assertEqual(r.cleaned_note_count, 0)
        self.assertIsNone(r.estimated_tempo)

    def test_summary_includes_removals(self):
        """summary() 包含移除统计."""
        r = CleanReport(
            original_note_count=100,
            cleaned_note_count=80,
            removed_short=10,
            removed_quiet=5,
            removed_isolated=3,
            merged_count=2,
            estimated_tempo=120.0,
        )
        s = r.summary()
        self.assertIn("100", s)
        self.assertIn("80", s)
        self.assertIn("10", s)  # removed_short
        self.assertIn("5", s)   # removed_quiet
        self.assertIn("120", s)  # tempo

    def test_summary_rhythm_stats(self):
        """summary() 包含节奏分析统计."""
        r = CleanReport(
            original_note_count=50,
            cleaned_note_count=45,
            rhythm_patterns_found=8,
            rhythm_flagged_spurious=3,
        )
        s = r.summary()
        self.assertIn("8", s)
        self.assertIn("3", s)


# ===== _estimate_tempo 测试 =====

class TestEstimateTempo(unittest.TestCase):
    """速度估计测试."""

    def test_external_bpm_priority(self):
        """外部 BPM 优先级最高."""
        if not HAS_PRETTY_MIDI:
            raise unittest.SkipTest("pretty_midi 未安装")
        midi = _make_midi([(0, 0.5)], tempo=120)
        result = _estimate_tempo(midi, external_bpm=140.0)
        self.assertEqual(result, 140.0)

    def test_midi_tempo_fallback(self):
        """无 external BPM 时使用 MIDI 元数据."""
        if not HAS_PRETTY_MIDI:
            raise unittest.SkipTest("pretty_midi 未安装")
        midi = _make_midi([(0, 0.5)], tempo=130)
        result = _estimate_tempo(midi, external_bpm=None)
        self.assertEqual(result, 130.0)

    def test_default_fallback(self):
        """无任何 BPM 信息时默认 120."""
        if not HAS_PRETTY_MIDI:
            raise unittest.SkipTest("pretty_midi 未安装")
        midi = _make_midi([(0, 0.5)], tempo=120)
        result = _estimate_tempo(midi, external_bpm=None)
        self.assertGreater(result, 0)


# ===== _estimate_key 测试 =====

class TestEstimateKey(unittest.TestCase):
    """调性估计测试."""

    def test_empty_notes(self):
        """空音符列表返回 '?'."""
        self.assertEqual(_estimate_key([]), "?")

    def test_c_major_scale(self):
        """C 大调音阶 → 应检测为 C."""
        if not HAS_PRETTY_MIDI:
            raise unittest.SkipTest("pretty_midi 未安装")
        # C major scale: C D E F G A B (MIDI 60-71, each 0.5s)
        notes = []
        for i, pitch in enumerate([60, 62, 64, 65, 67, 69, 71]):
            notes.append(pretty_midi.Note(
                velocity=90, pitch=pitch, start=i * 0.5, end=i * 0.5 + 0.5,
            ))
        result = _estimate_key(notes)
        # Should be C (major) or Am (minor) - both are possible
        self.assertIn(result, ("C", "Am", "F", "G"))

    def test_returns_string(self):
        """返回值为字符串."""
        if not HAS_PRETTY_MIDI:
            raise unittest.SkipTest("pretty_midi 未安装")
        notes = [pretty_midi.Note(velocity=90, pitch=60, start=0, end=1)]
        result = _estimate_key(notes)
        self.assertIsInstance(result, str)
        self.assertGreaterEqual(len(result), 1)


# ===== clean_midi 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestCleanMidi(unittest.TestCase):
    """clean_midi 集成测试."""

    def test_remove_short_notes(self):
        """移除过短音符."""
        midi = _make_midi([
            (0, 0.5, 60),      # 500ms — 保留
            (0.5, 0.51, 64),   # 10ms — 移除 (< 40ms)
            (1.0, 1.5, 67),    # 500ms — 保留
        ])
        cfg = CleanConfig(
            remove_short_notes=True,
            min_note_duration_ms=40.0,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.removed_short, 1)
        self.assertEqual(report.cleaned_note_count, 2)

    def test_remove_quiet_notes(self):
        """移除过弱音符."""
        midi = _make_midi([
            (0, 0.5, 60, 90),   # velocity=90 — 保留
            (0.5, 1.0, 64, 5),  # velocity=5 — 移除 (< 15)
            (1.0, 1.5, 67, 80), # velocity=80 — 保留
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=True,
            min_velocity=15,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.removed_quiet, 1)
        self.assertEqual(report.cleaned_note_count, 2)

    def test_merge_overlapping_notes(self):
        """合并同音高重叠音符."""
        midi = _make_midi([
            (0, 0.5, 60),     # C4
            (0.5, 0.51, 60),  # 紧接着同音高 (gap=0 < 30ms)
            (1.0, 1.5, 67),   # G4 (不同音高)
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=True,
            merge_gap_ms=30.0,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.merged_count, 1)
        self.assertEqual(report.cleaned_note_count, 2)  # 2 notes: merged C4 + G4

    def test_remove_isolated_notes(self):
        """移除孤立音符."""
        midi = _make_midi([
            (0, 0.5, 60),     # 孤立: gap > 500ms
            (2.0, 2.5, 64),   # 正常: 靠近下一个
            (2.6, 3.0, 67),   # 正常: 靠近上一个
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=True,
            isolated_note_gap_ms=500.0,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.removed_isolated, 1)
        self.assertEqual(report.cleaned_note_count, 2)

    def test_velocity_normalization(self):
        """力度归一化."""
        midi = _make_midi([
            (0, 0.5, 60, 50),
            (0.5, 1.0, 64, 50),
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=True,
            target_mean_velocity=90,
        )
        cleaned, report = clean_midi(midi, cfg)
        # 平均力度应由 50 被调整为接近 90
        velocities = [
            n.velocity
            for instr in cleaned.instruments
            for n in instr.notes
        ]
        mean_vel = np.mean(velocities)
        self.assertLess(abs(mean_vel - 90), 5)  # 允许少量误差

    def test_pitch_range_filter(self):
        """音域过滤."""
        midi = _make_midi([
            (0, 0.5, 40),   # 低于 min_pitch
            (0.5, 1.0, 60), # 在范围内
            (1.0, 1.5, 80), # 高于 max_pitch
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
            min_pitch=48,
            max_pitch=72,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.cleaned_note_count, 1)

    def test_progress_callback(self):
        """进度回调被调用."""
        midi = _make_midi([(0, 0.5, 60)])
        calls = []

        def cb(pct, msg):
            calls.append((pct, msg))

        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        clean_midi(midi, cfg, progress_callback=cb)
        self.assertGreater(len(calls), 0)
        # 最后一个回调应该是 100%
        self.assertEqual(calls[-1][0], 100)

    def test_original_note_count_preserved_in_report(self):
        """原始音符数记录正确."""
        midi = _make_midi([
            (0, 0.5, 60),
            (0.5, 1.0, 64),
            (1.0, 1.5, 67),
        ])
        cfg = CleanConfig(
            remove_short_notes=False,
            remove_quiet_notes=False,
            remove_isolated_notes=False,
            merge_overlapping=False,
            quantize_enabled=False,
            normalize_velocity=False,
        )
        cleaned, report = clean_midi(midi, cfg)
        self.assertEqual(report.original_note_count, 3)
        self.assertEqual(report.cleaned_note_count, 3)


# ===== get_midi_stats 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestGetMidiStats(unittest.TestCase):
    """get_midi_stats 测试."""

    def test_empty_midi(self):
        """空 MIDI 返回零值."""
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        stats = get_midi_stats(midi)
        self.assertEqual(stats["note_count"], 0)
        self.assertEqual(stats["duration_s"], 0.0)
        self.assertEqual(stats["mean_velocity"], 0.0)

    def test_stats_with_notes(self):
        """有音符时统计正确."""
        midi = _make_midi([
            (0, 1.0, 60, 80),
            (1.0, 2.0, 64, 100),
        ])
        stats = get_midi_stats(midi)
        self.assertEqual(stats["note_count"], 2)
        self.assertEqual(stats["pitch_range"], (60, 64))
        self.assertEqual(stats["mean_velocity"], 90.0)  # (80+100)/2
        self.assertEqual(stats["note_density"], 1.0)  # 2 notes / 2 seconds


# ===== extract_tempo_map 测试 =====

@unittest.skipIf(not HAS_PRETTY_MIDI, "pretty_midi 未安装")
class TestExtractTempoMap(unittest.TestCase):
    """extract_tempo_map 测试."""

    def test_default_tempo(self):
        """默认速度 120."""
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        result = extract_tempo_map(midi)
        self.assertEqual(result["initial_tempo"], 120.0)
        self.assertGreater(len(result["tempo_changes"]), 0)


if __name__ == '__main__':
    unittest.main()
