"""乐谱生成模块 / Music notation generation module.

Phase 3 — MIDI → 乐谱 (五线谱 / 简谱 / 六线谱 / 总谱)
"""

from src.core.notation.midi_to_score import (
    midi_to_score,
    split_midi_parts,
    detect_key_and_tempo,
)

from src.core.notation.notation_formats import (
    NotationFormat,
    NotationResult,
    generate_staff,
    generate_jianpu,
    generate_tablature,
    generate_full_score,
    generate_all_formats,
)

from src.core.notation.lilypond_exporter import (
    LilyPondExporter,
    LilyPondTemplate,
    export_ly_file,
    compile_lilypond,
    compile_to_pdf,
)

__all__ = [
    # midi_to_score
    "midi_to_score",
    "split_midi_parts",
    "detect_key_and_tempo",
    # notation_formats
    "NotationFormat",
    "NotationResult",
    "generate_staff",
    "generate_jianpu",
    "generate_tablature",
    "generate_full_score",
    "generate_all_formats",
    # lilypond_exporter
    "LilyPondExporter",
    "LilyPondTemplate",
    "export_ly_file",
    "compile_lilypond",
    "compile_to_pdf",
]
