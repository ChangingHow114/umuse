"""四种乐谱格式生成器 / Four notation format generators.

支持: 五线谱 (Staff) / 简谱 (Jianpu) / 六线谱 (Tablature) / 总谱 (Full Score)

每种格式输出 PDF + MusicXML，可在 MuseScore/LilyPond 中打开编辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import music21
from music21 import stream, note, chord, instrument, key, meter, tempo, clef


# ===== 数据类型 =====

class NotationFormat(Enum):
    """乐谱格式枚举 / Notation format enum."""
    STAFF = "staff"          # 五线谱
    JIANPU = "jianpu"        # 简谱 (数字谱)
    TABLATURE = "tablature"  # 六线谱 (吉他/贝斯指位谱)
    FULL_SCORE = "full_score"  # 总谱 (多声部合排)


@dataclass
class NotationResult:
    """乐谱生成结果 / Notation generation result.

    Attributes:
        format: 谱式类型
        pdf_path: PDF 文件路径 (如果编译成功)
        musicxml_path: MusicXML 文件路径 (可在 MuseScore 中编辑)
        ly_path: LilyPond 源文件路径 (如适用)
        note_count: 音符总数
        measure_count: 小节数
        errors: 警告/错误列表
    """
    format: NotationFormat
    pdf_path: Path | None = None
    musicxml_path: Path | None = None
    ly_path: Path | None = None
    note_count: int = 0
    measure_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.pdf_path is not None or self.musicxml_path is not None

    def summary(self) -> str:
        """生成中文摘要."""
        format_names = {
            NotationFormat.STAFF: "五线谱",
            NotationFormat.JIANPU: "简谱",
            NotationFormat.TABLATURE: "六线谱",
            NotationFormat.FULL_SCORE: "总谱",
        }
        name = format_names.get(self.format, self.format.value)
        lines = [f"  [{name}] {self.note_count} 音符, {self.measure_count} 小节"]
        if self.pdf_path:
            lines.append(f"    PDF: {self.pdf_path.name}")
        if self.musicxml_path:
            lines.append(f"    MusicXML: {self.musicxml_path.name}")
        if self.errors:
            lines.append(f"    警告: {len(self.errors)} 条")
        return "\n".join(lines)


# ===== 格式生成函数 =====

def generate_staff(
    score: music21.stream.Score,
    output_dir: Path | str,
    title: str = "Untitled",
    composer: str = "",
    compile_pdf: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> NotationResult:
    """生成五线谱 / Generate standard staff notation.

    输出标准五线谱，支持所有乐器，可导出 PDF + MusicXML。

    Args:
        score: music21 Score 对象
        output_dir: 输出目录
        title: 乐曲标题
        composer: 作曲者
        compile_pdf: 是否编译 PDF (需要 LilyPond)
        progress_callback: 进度回调

    Returns:
        NotationResult
    """
    from src.core.notation.lilypond_exporter import compile_to_pdf

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    if progress_callback:
        progress_callback(10, "准备五线谱...")

    # 深拷贝避免修改原 Score
    work_score = copy_score(score)

    # 添加曲目信息
    md = work_score.metadata or music21.metadata.Metadata()
    md.title = title
    if composer:
        md.composer = composer
    work_score.metadata = md

    # 统计信息
    note_count = count_notes(work_score)
    measure_count = count_measures(work_score)

    result = NotationResult(
        format=NotationFormat.STAFF,
        note_count=note_count,
        measure_count=measure_count,
    )

    # 导出 MusicXML (兼容 MuseScore/Sibelius/Finale)
    if progress_callback:
        progress_callback(30, "导出 MusicXML...")
    try:
        mxl_path = output_dir / f"{safe_filename(title)}_staff.musicxml"
        work_score.write('musicxml', fp=str(mxl_path))
        result.musicxml_path = mxl_path
    except Exception as e:
        errors.append(f"MusicXML 导出失败: {e}")

    # 导出 LilyPond + 编译 PDF
    if compile_pdf:
        if progress_callback:
            progress_callback(50, "生成 LilyPond 源码...")
        try:
            from src.core.notation.lilypond_exporter import LilyPondExporter
            exporter = LilyPondExporter()
            ly_path = output_dir / f"{safe_filename(title)}_staff.ly"
            ly_path = exporter.export_ly(work_score, ly_path, title, composer)
            result.ly_path = ly_path

            if progress_callback:
                progress_callback(70, "编译 PDF...")
            pdf_path = compile_to_pdf(ly_path, output_dir)
            result.pdf_path = pdf_path
        except Exception as e:
            errors.append(f"PDF 编译失败: {e}")

    if progress_callback:
        progress_callback(100, f"五线谱完成: {note_count} 音符")

    result.errors = errors
    return result


def generate_jianpu(
    score: music21.stream.Score,
    output_dir: Path | str,
    title: str = "Untitled",
    compile_pdf: bool = True,
    key_name: str = "C",
    progress_callback: Callable[[int, str], None] | None = None,
) -> NotationResult:
    """生成简谱 / Generate jianpu (numbered musical notation).

    使用 jianpu-ly 库将 music21 Score 转换为简谱 LilyPond 源文件，
    再编译为 PDF。简谱用 1-7 数字表示音阶，上/下加点表示高/低八度。

    Args:
        score: music21 Score 对象
        output_dir: 输出目录
        title: 乐曲标题
        compile_pdf: 是否编译 PDF
        key_name: 调性名称 (如 'C', 'D', 'G' 等)
        progress_callback: 进度回调

    Returns:
        NotationResult
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    if progress_callback:
        progress_callback(10, "提取旋律...")

    # 提取旋律 (只取最高音)
    melody = _extract_melody(score)

    note_count = count_notes(melody)
    measure_count = count_measures(melody)

    result = NotationResult(
        format=NotationFormat.JIANPU,
        note_count=note_count,
        measure_count=measure_count,
    )

    if progress_callback:
        progress_callback(30, "转换简谱...")

    # 生成 jianpu-ly 代码
    try:
        jianpu_ly = _score_to_jianpu_ly(melody, title=title, key_name=key_name)
    except Exception as e:
        errors.append(f"简谱转换失败: {e}")
        result.errors = errors
        return result

    # 保存 .ly 文件
    ly_path = output_dir / f"{safe_filename(title)}_jianpu.ly"
    ly_path.write_text(jianpu_ly, encoding='utf-8')
    result.ly_path = ly_path

    # 编译 PDF
    if compile_pdf:
        if progress_callback:
            progress_callback(60, "编译简谱 PDF...")
        try:
            from src.core.notation.lilypond_exporter import compile_to_pdf
            pdf_path = compile_to_pdf(ly_path, output_dir)
            result.pdf_path = pdf_path
        except Exception as e:
            errors.append(f"简谱 PDF 编译失败: {e}")

    # 也导出 MusicXML 版本 (五线谱格式，方便对比)
    if progress_callback:
        progress_callback(80, "导出 MusicXML...")
    try:
        mxl = output_dir / f"{safe_filename(title)}_jianpu.musicxml"
        score.write('musicxml', fp=str(mxl))
        result.musicxml_path = mxl
    except Exception as e:
        errors.append(f"MusicXML 导出失败: {e}")

    if progress_callback:
        progress_callback(100, f"简谱完成: {note_count} 音符")

    result.errors = errors
    return result


def generate_tablature(
    score: music21.stream.Score,
    output_dir: Path | str,
    title: str = "Untitled",
    instrument_type: str = "guitar",  # 'guitar' 或 'bass'
    compile_pdf: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> NotationResult:
    """生成六线谱 / Generate guitar/bass tablature.

    将 MIDI 音符映射到吉他/贝斯指板，输出六线谱 + 五线谱对照。

    Args:
        score: music21 Score 对象
        output_dir: 输出目录
        title: 乐曲标题
        instrument_type: 'guitar' (6弦) 或 'bass' (4弦)
        compile_pdf: 是否编译 PDF
        progress_callback: 进度回调

    Returns:
        NotationResult
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    work_score = copy_score(score)

    if progress_callback:
        progress_callback(10, f"映射{instrument_type}指板...")

    # 创建 tablature staff
    tab_part = _create_tablature_part(work_score, instrument_type)

    if tab_part is None:
        errors.append(f"无法为 {instrument_type} 生成指板映射")
        return NotationResult(
            format=NotationFormat.TABLATURE,
            errors=errors,
        )

    # 构建双谱表 Score: 五线谱 + 六线谱
    combined = stream.Score()
    md = combined.metadata or music21.metadata.Metadata()
    md.title = title
    combined.metadata = md

    # 添加原始五线谱 part
    for part in work_score.parts:
        combined.insert(0, part)

    # 添加六线谱 part
    combined.insert(0, tab_part)

    note_count = count_notes(combined)
    measure_count = count_measures(combined)

    result = NotationResult(
        format=NotationFormat.TABLATURE,
        note_count=note_count,
        measure_count=measure_count,
    )

    # 导出 MusicXML
    if progress_callback:
        progress_callback(50, "导出 MusicXML...")
    try:
        mxl_path = output_dir / f"{safe_filename(title)}_tab.musicxml"
        combined.write('musicxml', fp=str(mxl_path))
        result.musicxml_path = mxl_path
    except Exception as e:
        errors.append(f"MusicXML 导出失败: {e}")

    # 导出 LilyPond + 编译 PDF
    if compile_pdf:
        if progress_callback:
            progress_callback(70, "编译六线谱 PDF...")
        try:
            from src.core.notation.lilypond_exporter import compile_to_pdf
            ly_path = output_dir / f"{safe_filename(title)}_tab.ly"
            ly_path_no_ext = ly_path.with_suffix('')
            combined.write('lilypond', fp=str(ly_path_no_ext))
            # music21 writes without .ly extension — rename
            if ly_path_no_ext.exists() and not ly_path.exists():
                ly_path_no_ext.rename(ly_path)
                result.ly_path = ly_path
            elif ly_path.exists():
                result.ly_path = ly_path
            pdf_path = compile_to_pdf(ly_path, output_dir)
            result.pdf_path = pdf_path
        except Exception as e:
            errors.append(f"六线谱 PDF 编译失败: {e}")

    if progress_callback:
        progress_callback(100, f"六线谱完成: {note_count} 音符")

    result.errors = errors
    return result


def generate_full_score(
    scores: dict[str, music21.stream.Score],
    output_dir: Path | str,
    title: str = "Untitled",
    composer: str = "",
    compile_pdf: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> NotationResult:
    """生成总谱 / Generate full score (multi-part ensemble).

    将多个声部合并到同一总谱中，所有乐器纵向对齐。

    Args:
        scores: {声部名: music21 Score} 字典
        output_dir: 输出目录
        title: 乐曲标题
        composer: 作曲者
        compile_pdf: 是否编译 PDF
        progress_callback: 进度回调

    Returns:
        NotationResult
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    full_score = stream.Score()

    # 元数据
    md = full_score.metadata or music21.metadata.Metadata()
    md.title = title
    if composer:
        md.composer = composer
    full_score.metadata = md

    # 声部中文名映射
    instrument_map = {
        'piano': ('Piano', instrument.Piano()),
        'guitar': ('Guitar', instrument.AcousticGuitar()),
        'bass': ('Bass', instrument.ElectricBass()),
        'vocals': ('Voice', instrument.Vocalist()),
        'drums': ('Drums', instrument.Percussion()),
        'other': ('Other', instrument.Instrument()),
    }

    if progress_callback:
        progress_callback(10, "合并声部...")

    n_parts = len(scores)
    for i, (part_name, part_score) in enumerate(scores.items()):
        if progress_callback:
            pct = 10 + int(i / max(n_parts, 1) * 50)
            progress_callback(pct, f"处理 {part_name}...")

        part_score = copy_score(part_score)

        # 获取乐器配置
        inst_info = instrument_map.get(
            part_name,
            (part_name.capitalize(), instrument.Instrument()),
        )
        inst_label, inst_obj = inst_info

        # 为每个 Part 设置乐器
        for part in part_score.parts:
            part.partName = inst_label
            part.partAbbreviation = inst_label[:3]
            part.insert(0, inst_obj)
            full_score.insert(0, part)

    note_count = count_notes(full_score)
    measure_count = count_measures(full_score)

    result = NotationResult(
        format=NotationFormat.FULL_SCORE,
        note_count=note_count,
        measure_count=measure_count,
    )

    # 导出 MusicXML (可在 MuseScore 中完美打开总谱)
    if progress_callback:
        progress_callback(70, "导出 MusicXML 总谱...")
    try:
        mxl_path = output_dir / f"{safe_filename(title)}_full_score.musicxml"
        full_score.write('musicxml', fp=str(mxl_path))
        result.musicxml_path = mxl_path
    except Exception as e:
        errors.append(f"MusicXML 导出失败: {e}")

    # 导出 LilyPond
    if compile_pdf:
        if progress_callback:
            progress_callback(85, "编译总谱 PDF...")
        try:
            from src.core.notation.lilypond_exporter import compile_to_pdf
            ly_path = output_dir / f"{safe_filename(title)}_full_score.ly"
            ly_path_no_ext = ly_path.with_suffix('')
            full_score.write('lilypond', fp=str(ly_path_no_ext))
            # music21 writes without .ly extension — rename
            if ly_path_no_ext.exists() and not ly_path.exists():
                ly_path_no_ext.rename(ly_path)
                result.ly_path = ly_path
            elif ly_path.exists():
                result.ly_path = ly_path
            pdf_path = compile_to_pdf(ly_path, output_dir)
            result.pdf_path = pdf_path
        except Exception as e:
            errors.append(f"总谱 PDF 编译失败: {e}")

    if progress_callback:
        progress_callback(100, f"总谱完成: {n_parts} 声部, {note_count} 音符")

    result.errors = errors
    return result


def generate_all_formats(
    scores: dict[str, music21.stream.Score],
    output_dir: Path | str,
    title: str = "Untitled",
    composer: str = "",
    formats: list[NotationFormat] | None = None,
    compile_pdf: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[NotationFormat, NotationResult]:
    """生成所有指定谱式 / Generate all specified notation formats.

    Args:
        scores: {声部名: music21 Score} 字典
        output_dir: 输出目录
        title: 乐曲标题
        composer: 作曲者
        formats: 要生成的格式列表 (默认全部四种)
        compile_pdf: 是否编译 PDF
        progress_callback: 进度回调

    Returns:
        {NotationFormat: NotationResult}
    """
    if formats is None:
        formats = list(NotationFormat)

    results: dict[NotationFormat, NotationResult] = {}
    n_formats = len(formats)

    # 取第一个旋律声部用于简谱
    melodic_parts = {k: v for k, v in scores.items() if k != 'drums'}
    first_melodic = next(iter(melodic_parts.values())) if melodic_parts else None

    for i, fmt in enumerate(formats):
        pct_base = i / n_formats * 100

        def fmt_progress(pct: int, msg: str) -> None:
            total = int(pct_base + pct / n_formats)
            if progress_callback:
                progress_callback(total, f"[{fmt.value}] {msg}")

        if fmt == NotationFormat.STAFF:
            if first_melodic:
                results[fmt] = generate_staff(
                    first_melodic, output_dir, title, composer,
                    compile_pdf, fmt_progress,
                )

        elif fmt == NotationFormat.JIANPU:
            if first_melodic:
                # 检测调性
                key_info = first_melodic.analyze('key')
                results[fmt] = generate_jianpu(
                    first_melodic, output_dir, title,
                    compile_pdf, str(key_info.tonic.name) if key_info else 'C',
                    fmt_progress,
                )

        elif fmt == NotationFormat.TABLATURE:
            # 检查是否有吉他/贝斯
            tab_target = scores.get('guitar') or scores.get('bass')
            if tab_target:
                inst = 'bass' if 'bass' in scores else 'guitar'
                results[fmt] = generate_tablature(
                    tab_target, output_dir, title, inst,
                    compile_pdf, fmt_progress,
                )

        elif fmt == NotationFormat.FULL_SCORE:
            results[fmt] = generate_full_score(
                scores, output_dir, title, composer,
                compile_pdf, fmt_progress,
            )

    return results


# ===== 内部辅助函数 =====

def copy_score(score: music21.stream.Score) -> music21.stream.Score:
    """深拷贝 Score (music21 可能没有标准 __deepcopy__)."""
    # 通过 MusicXML 序列化/反序列化是最可靠的方式
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp_path = Path(tmp.name)
    try:
        score.write('musicxml', fp=str(tmp_path.with_suffix('')))
        copied = music21.converter.parse(str(tmp_path))
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
    if isinstance(copied, stream.Score):
        return copied
    s = stream.Score()
    s.insert(0, copied)
    return s


def count_notes(score_or_stream) -> int:
    """统计音符数量 / Count total notes."""
    return len(list(score_or_stream.recurse().notes))


def count_measures(score_or_stream) -> int:
    """统计小节数量 / Count total measures."""
    return len(list(score_or_stream.recurse().getElementsByClass(stream.Measure)))


def safe_filename(name: str) -> str:
    """生成安全的文件名 / Generate safe filename."""
    import re
    # 替换不安全字符
    safe = re.sub(r'[<>:"/\\|?*\s]+', '_', name.strip())
    return safe or "untitled"


def _jianpu_duration_prefix(quarter_length: float) -> str:
    """Convert music21 quarterLength to jianpu-ly duration prefix.

    jianpu-ly prefixes: s=16th, q=8th, (none)=quarter, c=half, d=whole.
    Can combine with dots: 's.' = dotted 16th, 'q.' = dotted 8th, '.' = dotted quarter.
    """
    standard = [
        (0.25, 's'),     # 16th note
        (0.375, 's.'),   # dotted 16th
        (0.5, 'q'),      # 8th note
        (0.75, 'q.'),    # dotted 8th
        (1.0, ''),       # quarter note
        (1.5, '.'),      # dotted quarter
        (2.0, 'c'),      # half note
        (3.0, 'c.'),     # dotted half
        (4.0, 'd'),      # whole note
        (6.0, 'd.'),     # dotted whole
    ]
    best = min(standard, key=lambda x: abs(x[0] - quarter_length))
    return best[1]


def _extract_melody(score: music21.stream.Score) -> music21.stream.Score:
    """从 Score 中提取主旋律 (取音高最高的声部) / Extract main melody."""
    # 直接返回 Score — 简谱转换会在 _score_to_jianpu_ly 中处理
    return score


def _score_to_jianpu_ly(
    score: music21.stream.Score,
    title: str = "Untitled",
    key_name: str = "C",
) -> str:
    """将 music21 Score 转换为 jianpu-ly 格式字符串.

    jianpu-ly 是一个 Python 库，接收类似 LilyPond 的文本标记生成简谱。
    这里直接生成 jianpu-ly 代码。

    Args:
        score: music21 Score
        title: 标题
        key_name: 调性名

    Returns:
        jianpu-ly LilyPond 源码字符串
    """
    # Build jianpu-ly input with KeepLength + duration prefixes
    # to preserve rhythmic information from the MIDI score.
    all_notes = list(score.recurse().notes)

    if not all_notes:
        import jianpu_ly as jply
        ly_code = jply.process_input("0")
        return _inject_jianpu_title(ly_code, title)

    jianpu_parts: list[str] = ["KeepLength"]
    total_duration: float = 0.0

    for n in all_notes:
        ql = n.quarterLength if n.quarterLength else 1.0
        total_duration += ql
        prefix = _jianpu_duration_prefix(ql)

        if n.isRest:
            jianpu_parts.append(f"{prefix}0")
            continue

        if isinstance(n, chord.Chord):
            pitch_midi = max(p.midi for p in n.pitches)
        else:
            pitch_midi = n.pitch.midi

        # MIDI -> jianpu scale degree (movable-do, C-based)
        scale_degree = pitch_midi % 12
        degree_map = {
            0: '1', 2: '2', 4: '3', 5: '4',
            7: '5', 9: '6', 11: '7',
        }
        chromatic_map = {
            1: '#1', 3: 'b3', 6: '#4', 8: 'b6', 10: 'b7',
        }
        jp_note = degree_map.get(scale_degree) or chromatic_map.get(scale_degree, '1')

        # Octave marks
        octave_shift = (pitch_midi - 60) // 12
        if octave_shift >= 1:
            jp_note += "'" * octave_shift
        elif octave_shift <= -1:
            jp_note += "," * abs(octave_shift)

        jianpu_parts.append(f"{prefix}{jp_note}")

    # Pad incomplete final bar with rests (jianpu-ly requires complete bars)
    beats_per_bar = 4.0  # assume 4/4
    remainder = total_duration % beats_per_bar
    if remainder > 0 and remainder < beats_per_bar:
        pad_beats = beats_per_bar - remainder
        pad_prefix = _jianpu_duration_prefix(pad_beats)
        jianpu_parts.append(f"{pad_prefix}0")

    jianpu_str = ' '.join(jianpu_parts)

    # Use jianpu-ly process_input() to generate complete LilyPond source
    import jianpu_ly as jply
    try:
        ly_code = jply.process_input(jianpu_str)
    except Exception:
        ly_code = jply.process_input("1")

    return _inject_jianpu_title(ly_code, title)


def _inject_jianpu_title(ly_code: str, title: str) -> str:
    """Inject title into jianpu-ly generated LilyPond header."""
    import re
    title_header = (
        f'\\header {{\n'
        f'  title = "{title}"\n'
        f'  tagline = ##f\n'
        f'}}\n\n'
    )
    return re.sub(
        r'(\\score\\s*\\{)',
        lambda m: title_header + m.group(1),
        ly_code,
        count=1,
    )


def _create_tablature_part(
    score: music21.stream.Score,
    instrument_type: str = "guitar",
) -> music21.stream.Part | None:
    """创建六线谱 Part / Create tablature Part from score.

    使用 music21 内建的 Tablature 支持将音符映射到吉他和弦位。

    Args:
        score: music21 Score
        instrument_type: 'guitar' (EADGBE) 或 'bass' (EADG)

    Returns:
        TabStaff Part 或 None
    """
    # 标准调弦 (从最低弦到最高弦)
    tunings = {
        'guitar': ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'],
        'bass': ['E1', 'A1', 'D2', 'G2'],
    }

    if instrument_type not in tunings:
        return None

    tuning_pitches = tunings[instrument_type]

    # 提取所有音符
    all_notes = list(score.recurse().notes)
    if not all_notes:
        return None

    # 创建 TabStaff
    from music21 import tablature

    tab_staff = stream.Part()
    tab_staff.append(instrument.Guitar() if instrument_type == 'guitar' else instrument.ElectricBass())

    for n in all_notes:
        if n.isRest:
            tab_staff.append(note.Rest(quarterLength=n.quarterLength))
            continue

        # 获取音高
        if isinstance(n, chord.Chord):
            pitches = list(n.pitches)
        else:
            pitches = [n.pitch]

        # 为每个音找最佳弦位
        tab_notes = []
        for pitch in pitches:
            best_string, best_fret = _find_best_fret(pitch, tuning_pitches)
            if best_string is not None:
                tn = note.Note(pitch)
                # 设置弦位 (1-indexed, 1=最高音弦)
                tn.fret = best_fret
                tn.string = best_string
                tab_notes.append(tn)

        if tab_notes:
            if len(tab_notes) == 1:
                tn = tab_notes[0]
                tn.quarterLength = n.quarterLength
                tab_staff.append(tn)
            else:
                # 和弦 (多个音在同一位置)
                c = chord.Chord([tn.pitch for tn in tab_notes])
                c.quarterLength = n.quarterLength
                tab_staff.append(c)

    # 转换为 TabStaff context
    try:
        tab_staff.makeNotation(inPlace=True, tabNotation=True)
    except Exception:
        pass

    return tab_staff


def _find_best_fret(
    pitch: music21.pitch.Pitch,
    tuning: list[str],
) -> tuple[int | None, int | None]:
    """找最佳弦位 / Find best string and fret for a pitch.

    规则:
    - 优先低把位 (fret 0-5) 方便演奏
    - 避免超过 12 品
    - 能弹奏的弦中取最低 fret

    Args:
        pitch: 目标音高 (music21 Pitch)
        tuning: 空弦音高列表 (从低到高)

    Returns:
        (string_number, fret_number) 或 (None, None)
    """
    target = pitch.midi
    best_string = None
    best_fret = 99

    for i, open_string_pitch in enumerate(tuning):
        open_midi = music21.pitch.Pitch(open_string_pitch).midi
        fret = target - open_midi
        if 0 <= fret <= 15:  # 0=空弦, ≤15品
            if fret < best_fret:
                best_fret = fret
                best_string = i + 1  # 1-indexed

    if best_string is None:
        # 找离目标最近但高出>15品的那根弦
        for i, open_string_pitch in enumerate(tuning):
            open_midi = music21.pitch.Pitch(open_string_pitch).midi
            fret = target - open_midi
            if fret > 15 and fret < best_fret:
                best_fret = fret
                best_string = i + 1

    if best_string is None:
        return None, None

    return best_string, best_fret
