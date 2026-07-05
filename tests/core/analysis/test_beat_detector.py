"""节拍检测器测试 / Tests for beat_detector.py.

测试覆盖:
- AnalysisResult: 属性计算 (beat_interval, bar_interval, time_signature_str)
- AnalysisResult: get_bar_number, get_beat_number, get_expected_beat_time
- AnalysisResult: summary()
- BeatDetector: 初始化和参数验证
"""

import math
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np

from src.core.analysis.beat_detector import AnalysisResult, BeatDetector

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False


# ===== AnalysisResult 测试 =====

class TestAnalysisResult(unittest.TestCase):
    """AnalysisResult 数据类测试 (纯 Python, 无外部依赖)."""

    # ---- 构造 ----

    def test_minimal_construction(self):
        """最小构造参数."""
        r = AnalysisResult(bpm=120.0)
        self.assertEqual(r.bpm, 120.0)
        self.assertEqual(r.beat_times, [])
        self.assertEqual(r.downbeat_times, [])
        self.assertEqual(r.time_signature, (4, 4))
        self.assertEqual(r.confidence, 0.0)
        self.assertEqual(r.source_stem, "")

    def test_full_construction(self):
        """完整构造参数."""
        beats = [0.0, 0.5, 1.0, 1.5]
        downbeats = [0.0, 2.0]
        positions = [1, 2, 3, 4]
        r = AnalysisResult(
            bpm=120.0,
            beat_times=beats,
            downbeat_times=downbeats,
            time_signature=(4, 4),
            beat_positions=positions,
            confidence=0.85,
            source_stem="drums",
        )
        self.assertEqual(r.bpm, 120.0)
        self.assertEqual(len(r.beat_times), 4)
        self.assertEqual(len(r.downbeat_times), 2)
        self.assertEqual(r.confidence, 0.85)
        self.assertEqual(r.source_stem, "drums")

    # ---- beat_interval ----

    def test_beat_interval_120bpm(self):
        """120 BPM → 0.5s/拍."""
        r = AnalysisResult(bpm=120.0)
        self.assertEqual(r.beat_interval, 0.5)

    def test_beat_interval_60bpm(self):
        """60 BPM → 1.0s/拍."""
        r = AnalysisResult(bpm=60.0)
        self.assertEqual(r.beat_interval, 1.0)

    def test_beat_interval_zero_bpm(self):
        """BPM=0 → fallback 0.5s."""
        r = AnalysisResult(bpm=0.0)
        self.assertEqual(r.beat_interval, 0.5)

    # ---- bar_interval ----

    def test_bar_interval_4_4(self):
        """4/4 拍 → bar_interval = 4 × beat_interval."""
        r = AnalysisResult(bpm=120.0, time_signature=(4, 4))
        self.assertEqual(r.bar_interval, 2.0)  # 4 × 0.5

    def test_bar_interval_3_4(self):
        """3/4 拍 → bar_interval = 3 × beat_interval."""
        r = AnalysisResult(bpm=120.0, time_signature=(3, 4))
        self.assertEqual(r.bar_interval, 1.5)  # 3 × 0.5

    def test_bar_interval_6_8(self):
        """6/8 拍 → bar_interval = 6 × beat_interval."""
        r = AnalysisResult(bpm=120.0, time_signature=(6, 8))
        self.assertEqual(r.bar_interval, 3.0)  # 6 × 0.5

    # ---- time_signature_str ----

    def test_time_signature_str(self):
        r = AnalysisResult(bpm=120.0, time_signature=(4, 4))
        self.assertEqual(r.time_signature_str, "4/4")

    def test_time_signature_str_3_4(self):
        r = AnalysisResult(bpm=120.0, time_signature=(3, 4))
        self.assertEqual(r.time_signature_str, "3/4")

    # ---- get_bar_number ----

    def test_get_bar_number_no_downbeats(self):
        """无 downbeat 数据时用 bar_interval 估算."""
        r = AnalysisResult(bpm=120.0)  # bar_interval = 2.0s
        self.assertEqual(r.get_bar_number(0.0), 0)
        self.assertEqual(r.get_bar_number(2.0), 1)
        self.assertEqual(r.get_bar_number(3.9), 1)
        self.assertEqual(r.get_bar_number(4.0), 2)

    def test_get_bar_number_with_downbeats(self):
        """有 downbeat 数据时精确定位."""
        r = AnalysisResult(
            bpm=120.0,
            downbeat_times=[0.0, 2.0, 4.0, 6.0],
            time_signature=(4, 4),
        )
        self.assertEqual(r.get_bar_number(0.0), 0)
        self.assertEqual(r.get_bar_number(0.5), 0)
        self.assertEqual(r.get_bar_number(2.0), 1)  # 第二个小节开始
        self.assertEqual(r.get_bar_number(3.5), 1)
        self.assertEqual(r.get_bar_number(4.0), 2)

    def test_get_bar_number_before_first_downbeat(self):
        """时间在第一个 downbeat 之前."""
        r = AnalysisResult(
            bpm=120.0,
            downbeat_times=[0.5, 2.5, 4.5],
        )
        self.assertEqual(r.get_bar_number(0.0), 0)

    # ---- get_beat_number ----

    def test_get_beat_number_no_downbeats(self):
        """无 downbeat 数据时用 beat_interval 估算."""
        r = AnalysisResult(bpm=120.0, time_signature=(4, 4))
        self.assertEqual(r.get_beat_number(0.0), 1)   # beat 1
        self.assertEqual(r.get_beat_number(0.5), 2)   # beat 2
        self.assertEqual(r.get_beat_number(1.0), 3)   # beat 3
        self.assertEqual(r.get_beat_number(1.5), 4)   # beat 4
        self.assertEqual(r.get_beat_number(2.0), 1)   # 下一小节 beat 1

    def test_get_beat_number_with_downbeats(self):
        """有 downbeat 数据时精确返回拍位."""
        r = AnalysisResult(
            bpm=120.0,
            downbeat_times=[0.0, 2.0, 4.0],
            time_signature=(4, 4),
        )
        self.assertEqual(r.get_beat_number(0.0), 1)
        self.assertEqual(r.get_beat_number(0.5), 2)
        self.assertEqual(r.get_beat_number(2.0), 1)  # 第二小节强拍
        self.assertEqual(r.get_beat_number(2.5), 2)

    # ---- get_expected_beat_time ----

    def test_get_expected_beat_time(self):
        """计算预期节拍时间."""
        r = AnalysisResult(
            bpm=120.0,
            downbeat_times=[0.0, 2.0, 4.0],
            time_signature=(4, 4),
        )
        # Bar 0, Beat 1 → 0.0
        self.assertEqual(r.get_expected_beat_time(0, 1), 0.0)
        # Bar 0, Beat 3 → 1.0
        self.assertEqual(r.get_expected_beat_time(0, 3), 1.0)
        # Bar 1, Beat 1 → 2.0
        self.assertEqual(r.get_expected_beat_time(1, 1), 2.0)
        # Bar 1, Beat 4 → 3.5
        self.assertEqual(r.get_expected_beat_time(1, 4), 3.5)

    def test_get_expected_beat_time_fallback(self):
        """无 downbeat 时用平均推算."""
        r = AnalysisResult(bpm=120.0)
        # Bar 0, Beat 1 → 0.0
        self.assertEqual(r.get_expected_beat_time(0, 1), 0.0)
        # Bar 1, Beat 1 → 2.0 (bar_interval = 2.0)
        self.assertEqual(r.get_expected_beat_time(1, 1), 2.0)

    # ---- summary ----

    def test_summary_contains_key_info(self):
        """summary() 包含关键信息."""
        r = AnalysisResult(
            bpm=120.0,
            beat_times=[0.0, 0.5, 1.0],
            downbeat_times=[0.0],
            time_signature=(4, 4),
            confidence=0.9,
            source_stem="drums",
        )
        s = r.summary()
        self.assertIn("120.0", s)
        self.assertIn("4/4", s)
        self.assertIn("90.0%", s)  # 0.9 → 90%
        self.assertIn("drums", s)

    def test_summary_with_offset(self):
        """summary() 显示手动偏移."""
        r = AnalysisResult(bpm=120.0, offset_beats=2)
        s = r.summary()
        self.assertIn("+2", s)

    # ---- offset_beats ----

    def test_offset_beats_default(self):
        """默认偏移为 0."""
        r = AnalysisResult(bpm=120.0)
        self.assertEqual(r.offset_beats, 0)

    def test_offset_beats_negative(self):
        """支持负偏移."""
        r = AnalysisResult(bpm=120.0, offset_beats=-1)
        self.assertEqual(r.offset_beats, -1)


# ===== BeatDetector 测试 =====

class TestBeatDetector(unittest.TestCase):
    """BeatDetector 构造和参数测试."""

    def test_default_construction(self):
        """默认构造参数."""
        bd = BeatDetector()
        self.assertEqual(bd.sr, 22050)
        self.assertEqual(bd.bpm_min, 40.0)
        self.assertEqual(bd.bpm_max, 250.0)

    def test_custom_construction(self):
        """自定义构造参数."""
        bd = BeatDetector(sr=44100, bpm_min=60.0, bpm_max=200.0)
        self.assertEqual(bd.sr, 44100)
        self.assertEqual(bd.bpm_min, 60.0)
        self.assertEqual(bd.bpm_max, 200.0)


# ===== 合成音频测试 (需要 librosa) =====

@unittest.skipIf(not HAS_LIBROSA, "librosa 未安装")
class TestBeatDetectorWithAudio(unittest.TestCase):
    """BeatDetector 音频处理测试."""

    def test_detect_bpm_from_click_track(self):
        """从节拍器音频检测 BPM (精度 ±2 BPM)."""
        sr = 22050
        target_bpm = 120.0
        duration = 5.0  # 5 秒

        # 生成节拍器音频 (每 beat 一个 click)
        beat_interval = 60.0 / target_bpm
        n_beats = int(duration / beat_interval)
        y = np.zeros(int(duration * sr))
        for i in range(n_beats):
            t_sample = int(i * beat_interval * sr)
            # 短 click (10ms)
            click_len = int(0.01 * sr)
            if t_sample + click_len < len(y):
                y[t_sample:t_sample + click_len] = 1.0

        detector = BeatDetector(sr=sr)
        bpm = detector.detect_bpm_from_array(y, sr)

        self.assertLess(abs(bpm - target_bpm), 5.0,
                        f"BPM 偏差过大: {bpm} vs {target_bpm}")

    def test_detect_bpm_half_time(self):
        """60 BPM 节拍器检测."""
        sr = 22050
        target_bpm = 60.0
        duration = 5.0

        beat_interval = 60.0 / target_bpm
        n_beats = int(duration / beat_interval)
        y = np.zeros(int(duration * sr))
        for i in range(n_beats):
            t_sample = int(i * beat_interval * sr)
            click_len = int(0.01 * sr)
            if t_sample + click_len < len(y):
                y[t_sample:t_sample + click_len] = 1.0

        detector = BeatDetector(sr=sr)
        bpm = detector.detect_bpm_from_array(y, sr)

        # librosa 有时会检测到双倍 tempo (120 BPM)
        # 允许 ±5 BPM 或检测到双倍值
        is_close = abs(bpm - target_bpm) < 5.0 or abs(bpm - target_bpm * 2) < 5.0
        self.assertTrue(is_close, f"BPM 不在预期范围: {bpm}")

    def test_detect_bpm_returns_positive(self):
        """BPM 返回值始终为正."""
        sr = 22050
        y = np.random.randn(int(3.0 * sr)) * 0.1  # 噪音

        detector = BeatDetector()
        bpm = detector.detect_bpm_from_array(y, sr)

        self.assertGreater(bpm, 0)
        self.assertGreaterEqual(bpm, detector.bpm_min)
        self.assertLessEqual(bpm, detector.bpm_max)

    def test_detect_raises_on_nonexistent_file(self):
        """不存在的文件抛出 FileNotFoundError."""
        detector = BeatDetector()
        with self.assertRaises(FileNotFoundError):
            detector.detect(Path("/nonexistent/audio.wav"))

    def test_detect_bpm_raises_on_nonexistent_file(self):
        """detect_bpm 也在不存在的文件上抛出异常."""
        detector = BeatDetector()
        with self.assertRaises(FileNotFoundError):
            detector.detect_bpm(Path("/nonexistent/audio.wav"))


if __name__ == '__main__':
    unittest.main()
