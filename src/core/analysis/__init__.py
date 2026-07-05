"""节奏分析模块 / Rhythm Analysis Module.

提供音频级别的节拍检测、强拍定位和节奏型分析功能。

用法:
    from src.core.analysis import BeatDetector, AnalysisResult
    detector = BeatDetector()
    result = detector.detect(audio_path)
    print(f"BPM: {result.bpm}, Confidence: {result.confidence}")

    from src.core.analysis.rhythm_analyzer import (
        RhythmReport, extract_rhythmic_patterns,
        flag_spurious_notes, merge_flagged_notes, section_review,
    )
"""

from __future__ import annotations

from src.core.analysis.beat_detector import BeatDetector, AnalysisResult

__all__ = [
    "BeatDetector",
    "AnalysisResult",
]
