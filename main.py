"""UMuse — AI 音乐逆向工程工作站.

入口文件，支持 CLI 和 GUI 两种模式。

CLI 用法:
    python main.py separate <audio_file> [-o output_dir] [--strategy vocal_priority]
    python main.py info <audio_file>

GUI 用法:
    python main.py --gui

完整流水线:
    python main.py pipeline <audio_file> -o output_dir
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 确保项目根目录在 Python Path 中
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def cmd_separate(args: argparse.Namespace) -> int:
    """CLI 分轨命令 / Separation command."""
    from src.core.audio.loader import validate_audio
    from src.core.project import Project, ProjectStatus
    from src.core.separation.audio_separator_runner import StemSeparator

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else _PROJECT_ROOT / "output"

    # 获取策略信息
    strategy = getattr(args, "strategy", "vocal_priority")
    strategies = StemSeparator.get_available_strategies()
    strategy_info = strategies.get(strategy, {})
    strategy_name = strategy_info.get("name", strategy)

    print(f"\n{'='*60}")
    print(f"  UMuse — 音频分轨")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_dir}")
    print(f"  策略: {strategy} ({strategy_name})")
    print(f"  设备: {args.device}")
    print(f"{'='*60}\n")

    # 验证输入
    result = validate_audio(str(input_path))
    if not result["valid"]:
        print(f"  [X] {result['reason']}")
        return 1
    print(f"  [OK] {result['reason']}")

    # 初始化项目
    project = Project(
        name=input_path.stem,
        input_file=input_path,
        output_dir=output_dir / input_path.stem,
    )
    project.ensure_output_dir()

    # 执行分轨
    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))  # clamp
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<30}", end="")

    separator = StemSeparator(device=args.device)
    stems = separator.separate(
        input_path=input_path,
        output_dir=project.output_dir,
        strategy=strategy,
        shifts=args.shifts,
        overlap=args.overlap,
        mp3=args.mp3,
        progress_callback=progress,
    )
    print()  # 换行

    # 更新 project
    for stem_name, stem_path in stems.items():
        project.stems[stem_name].path = stem_path

    project.set_status(ProjectStatus.SEPARATED)

    # 输出结果
    print(f"\n  [Done] 分轨完成! {len(stems)} 轨已分离:\n")
    stem_info = StemSeparator.get_stem_info("htdemucs_6s")
    for name, path in stems.items():
        zh = stem_info.get(name, name)
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"    [{zh}] ({name}): {path.name} ({size_mb:.1f} MB)")

    # 保存项目
    project_path = project.save()
    print(f"\n  [Save] 项目已保存: {project_path}")
    print()

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """CLI 音频信息命令."""
    from src.core.audio.loader import get_audio_info, validate_audio

    input_path = Path(args.input)
    print(f"\n  文件: {input_path}")
    print(f"  大小: {input_path.stat().st_size / (1024*1024):.1f} MB\n")

    result = validate_audio(str(input_path))
    if result["valid"]:
        info = get_audio_info(str(input_path))
        print(f"  时长: {info['duration_sec']:.1f} 秒")
        print(f"  采样率: {info['sample_rate']} Hz")
        print(f"  通道数: {info['channels']}")
        print(f"  帧数: {info['frames']}")
    else:
        print(f"  [X] {result['reason']}")

    print()
    return 0 if result["valid"] else 1


def cmd_pipeline(args: argparse.Namespace) -> int:
    """CLI 完整流水线 / Full pipeline."""
    from src.config.settings import Settings
    from src.core.audio.loader import validate_audio
    from src.core.project import Project, ProjectStatus
    from src.core.pipeline import PipelineManager

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else _PROJECT_ROOT / "output"

    result = validate_audio(str(input_path))
    if not result["valid"]:
        print(f"[X] {result['reason']}")
        return 1

    project = Project(
        name=input_path.stem,
        input_file=input_path,
        output_dir=output_dir / input_path.stem,
    )
    project.ensure_output_dir()

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    pm = PipelineManager(project)
    pm.run_full_pipeline(
        skip_transcription=args.no_transcribe,
        skip_drum_slicing=args.no_drums,
        skip_notation=args.no_notation,
        skip_timbre=args.no_matching,
        skip_effects=args.no_effects,
        skip_refinement=args.no_refinement,
        skip_beat_analysis=args.no_beat_analysis,
        progress_callback=progress,
    )
    print()

    project.save()
    print(f"\n  [Done] 流水线完成! 结果保存在: {project.output_dir}\n")
    print(project.summary())
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    """CLI MIDI 转录命令 / Transcription command."""
    from src.core.audio.loader import validate_audio
    from src.core.transcription import transcribe, clean_midi, CleanConfig

    stem_path = Path(args.stem)
    output_dir = Path(args.output) if args.output else stem_path.parent

    print(f"\n{'='*60}")
    print(f"  UMuse — MIDI 转录")
    print(f"  输入: {stem_path}")
    print(f"  输出: {output_dir}")
    print(f"  模型: basic-pitch ONNX")
    print(f"{'='*60}\n")

    if not stem_path.exists():
        print(f"  [X] 文件不存在: {stem_path}")
        return 1

    print(f"  [OK] 开始转录...\n")

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    result = transcribe(
        audio_path=stem_path,
        output_dir=output_dir,
        onset_threshold=args.onset_threshold,
        frame_threshold=args.frame_threshold,
        minimum_note_length=args.min_note_len,
        progress_callback=progress,
    )
    print()  # 换行

    print(f"\n  [Done] 转录完成! {len(result['note_events'])} 个音符")

    # 清洗
    if not args.no_clean:
        print(f"\n  [Clean] 后处理清洗中...")
        cleaned, report = clean_midi(
            result["midi_data"],
            CleanConfig(merge_overlapping=True, normalize_velocity=True),
        )
        if result["midi_path"]:
            cleaned.write(str(result["midi_path"]))
        print(f"  {report.summary()}")

    if result["midi_path"]:
        print(f"\n  [Save] MIDI 已保存: {result['midi_path']}")
    print()
    return 0


def cmd_drums(args: argparse.Namespace) -> int:
    """CLI 鼓组切片命令 / Drum slicing command."""
    from src.core.transcription import slice_drum_stem, export_drum_kit

    stem_path = Path(args.stem)
    output_dir = Path(args.output) if args.output else stem_path.parent / f"{stem_path.stem}_slices"

    print(f"\n{'='*60}")
    print(f"  UMuse — 鼓组采样切片")
    print(f"  输入: {stem_path}")
    print(f"  输出: {output_dir}")
    print(f"{'='*60}\n")

    if not stem_path.exists():
        print(f"  [X] 文件不存在: {stem_path}")
        return 1

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    result = slice_drum_stem(
        audio_path=stem_path,
        output_dir=output_dir,
        save_slices=True,
        save_by_type=True,
        onset_sensitivity=args.sensitivity,
        progress_callback=progress,
    )
    print()

    print(f"\n  {result.summary()}")

    # 导出精选鼓组
    kit_dir = output_dir / "drum_kit"
    kit = export_drum_kit(result, kit_dir, top_n_per_type=args.top_n)
    print(f"\n  [Kit] 精选鼓组: {kit_dir}")
    for dtype, paths in kit.items():
        print(f"    {dtype}: {len(paths)} 个")

    print(f"\n  [Save] 全部切片: {output_dir}\n")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    """CLI 音色匹配命令 / Timbre matching command."""
    from pathlib import Path
    from src.core.timbre import (
        FeatureExtractor, PresetDatabase, PresetMatcher, format_match_results,
    )

    # 初始化数据库
    db = PresetDatabase()

    if args.init_db:
        db._init_builtin_presets()
        db.save()
        print(f"已初始化 {db.count} 个内置预设")
        return 0
    else:
        db.load()
        if db.count == 0:
            print("预设数据库为空, 先初始化…")
            db._init_builtin_presets()
            db.save()

    if not args.stem:
        print("请指定 stem 音频文件或项目目录, 或用 --init-db 初始化数据库")
        return 1

    stem_path = Path(args.stem)

    # 判断输入是 stem 文件还是项目目录
    if stem_path.is_dir():
        from src.core.project import Project
        project_file = stem_path / "project.json"
        if not project_file.exists():
            print(f"[X] 项目文件不存在: {project_file}")
            return 1
        project = Project.load(project_file)
        melodic = ["piano", "guitar", "bass", "vocals"]
        for sname in melodic:
            stem_info = project.stems.get(sname)
            if not stem_info or not stem_info.path or not stem_info.path.exists():
                continue
            print(f"\n{'='*60}")
            print(f"  匹配 {sname}: {stem_info.path}")
            print(f"{'='*60}")
            _run_match(stem_info.path, db, args)
        return 0
    else:
        if not stem_path.exists():
            print(f"[X] 文件不存在: {stem_path}")
            return 1
        return _run_match(stem_path, db, args)


def _run_match(
    stem_path: Path,
    db: "PresetDatabase",
    args: argparse.Namespace,
) -> int:
    """对单个 stem 文件执行匹配."""
    from src.core.timbre import FeatureExtractor, PresetMatcher, format_match_results

    extractor = FeatureExtractor()
    matcher = PresetMatcher(db, extractor)

    print(f"\n  提取特征中…")
    features = extractor.extract(stem_path)
    print(f"  特征向量: {len(features)} 维")

    print(f"  匹配预设中…\n")
    results = matcher.match(
        features,
        top_k=args.top_k,
        instrument_filter=args.instrument,
    )

    if not results:
        print("  (无匹配结果)")
        return 1

    print(format_match_results(results))
    return 0


def cmd_effects(args: argparse.Namespace) -> int:
    """CLI 效果器分析命令 / Effects analysis command (Phase 5)."""
    from pathlib import Path
    from src.core.project import Project
    from src.core.pipeline import PipelineManager

    # 判断输入是 stem 文件还是项目目录
    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else _PROJECT_ROOT / "output"

    if input_path.is_dir():
        project_file = input_path / "project.json"
        if not project_file.exists():
            print(f"[X] 项目文件不存在: {project_file}")
            return 1
        project = Project.load(project_file)
    elif input_path.suffix.lower() in (".wav", ".mp3", ".flac"):
        # 单个 stem 文件: 创建临时项目
        project = Project(
            name=input_path.stem,
            input_file=None,
            output_dir=output_dir / input_path.stem,
        )
        project.ensure_output_dir()
        # 需要手动设置 stem
        from src.core.project import StemInfo
        stem_name = args.instrument or "piano"
        project.stems = {}
        project.stems[stem_name] = StemInfo(
            name=stem_name,
            name_zh={"piano": "钢琴", "guitar": "吉他", "bass": "贝斯", "vocals": "人声"}.get(stem_name, stem_name),
            path=input_path,
            is_melodic=True,
        )
        # 必须提供预设名
        if not args.preset:
            print("[X] 单 stem 模式需要 --preset 指定匹配到的预设名")
            return 1
        project.stems[stem_name].matched_presets = [{"preset_name": args.preset}]
    else:
        print(f"[X] 输入必须是 stem 文件或项目目录: {input_path}")
        return 1

    print(f"\n{'='*60}")
    print(f"  UMuse — 效果器参数预估 (Phase 5)")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_dir}")
    print(f"{'='*60}\n")

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    pm = PipelineManager(project)
    results = pm.run_effects_analysis(
        stem_name=args.instrument,
        preset_name=args.preset,
        progress_callback=progress,
    )
    print()

    for sname, profile in results.items():
        print(f"\n  [{sname}]")
        print(profile.summary())
        effects_path = project.output_dir / sname / "effects_params.json"
        if effects_path.exists():
            print(f"    → {effects_path}")

    project.save()
    print(f"\n  [Done] 效果器分析完成!\n")
    return 0


def cmd_refine(args: argparse.Namespace) -> int:
    """CLI 迭代精炼命令 / Refinement command (Phase 4→5→4)."""
    from pathlib import Path
    from src.core.project import Project
    from src.core.pipeline import PipelineManager
    from src.core.refinement import format_refinement_results

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else _PROJECT_ROOT / "output"

    if input_path.is_dir():
        project_file = input_path / "project.json"
        if not project_file.exists():
            print(f"[X] 项目文件不存在: {project_file}")
            return 1
        project = Project.load(project_file)
    elif input_path.suffix.lower() in (".wav", ".mp3", ".flac"):
        # 单个 stem → 先初始化预设数据库, 然后精炼
        from src.core.timbre import PresetDatabase
        from src.core.project import StemInfo

        db = PresetDatabase()
        db.load()
        if db.count == 0:
            db._init_builtin_presets()
            db.save()

        project = Project(
            name=input_path.stem,
            input_file=None,
            output_dir=output_dir / input_path.stem,
        )
        project.ensure_output_dir()
        stem_name = args.instrument or "piano"
        project.stems = {}
        project.stems[stem_name] = StemInfo(
            name=stem_name,
            name_zh={"piano": "钢琴", "guitar": "吉他", "bass": "贝斯", "vocals": "人声"}.get(stem_name, stem_name),
            path=input_path,
            is_melodic=True,
        )
    else:
        print(f"[X] 输入必须是 stem 文件或项目目录: {input_path}")
        return 1

    print(f"\n{'='*60}")
    print(f"  UMuse — 音色精炼 (Phase 4→5→4)")
    print(f"  输入: {input_path}")
    print(f"  最大迭代: {args.max_iter}")
    print(f"{'='*60}\n")

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    pm = PipelineManager(project)
    results = pm.run_refinement(
        stem_name=args.instrument,
        max_iterations=args.max_iter,
        progress_callback=progress,
    )
    print()

    print(format_refinement_results(results))

    project.save()
    print(f"\n  [Done] 精炼完成!\n")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    """启动 GUI / Launch GUI."""
    from src.gui.app import main as gui_main
    return gui_main()


def cmd_notation(args: argparse.Namespace) -> int:
    """CLI 乐谱生成命令 / Notation command."""
    from src.core.notation.midi_to_score import midi_to_score
    from src.core.notation.notation_formats import (
        NotationFormat, generate_staff, generate_jianpu,
        generate_tablature, generate_full_score, generate_all_formats,
    )
    from src.core.notation.lilypond_exporter import get_lilypond_path

    # Auto-detect LilyPond path (cross-platform)
    ly_path = get_lilypond_path()
    if not ly_path.exists():
        print(f"  [WARNING] LilyPond 未找到, PDF 编译将跳过")
        print(f"  安装: brew install lilypond (macOS) 或 apt install lilypond (Linux)")

    midi_path = Path(args.midi)
    output_dir = Path(args.output) if args.output else midi_path.parent / "notation"

    print(f"\n{'='*60}")
    print(f"  UMuse — 乐谱生成 (Phase 3)")
    print(f"  MIDI: {midi_path}")
    print(f"  输出: {output_dir}")
    print(f"  格式: {args.format}")
    print(f"{'='*60}\n")

    if not midi_path.exists():
        print(f"  [X] MIDI 文件不存在: {midi_path}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    def progress(pct: int, msg: str) -> None:
        pct = max(0, min(100, pct))
        bar_len = 40
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:3d}% | {msg:<40}", end="")

    print("  [1/2] 加载 MIDI → Score...")
    score = midi_to_score(midi_path, progress_callback=progress)
    print()

    print(f"  [2/2] 生成乐谱 ({args.format})...")
    title = args.title or midi_path.stem

    if args.format == "all":
        results = generate_all_formats(
            {"melody": score}, output_dir, title=title,
            compile_pdf=not args.no_pdf, progress_callback=progress,
        )
    elif args.format == "staff":
        results = {
            NotationFormat.STAFF: generate_staff(
                score, output_dir, title=title,
                compile_pdf=not args.no_pdf, progress_callback=progress,
            ),
        }
    elif args.format == "jianpu":
        results = {
            NotationFormat.JIANPU: generate_jianpu(
                score, output_dir, title=title,
                compile_pdf=not args.no_pdf, progress_callback=progress,
            ),
        }
    elif args.format == "full_score":
        results = {
            NotationFormat.FULL_SCORE: generate_full_score(
                {"melody": score}, output_dir, title=title,
                compile_pdf=not args.no_pdf, progress_callback=progress,
            ),
        }
    elif args.format == "tablature":
        results = {
            NotationFormat.TABLATURE: generate_tablature(
                score, output_dir, title=title,
                compile_pdf=not args.no_pdf, progress_callback=progress,
            ),
        }
    else:
        print(f"  [X] 不支持的格式: {args.format}")
        return 1

    print()

    # Summary
    print(f"\n  [Done] 乐谱生成完成!\n")
    for fmt, res in results.items():
        print(res.summary())
        if res.errors:
            for e in res.errors:
                print(f"    [WARNING] {e[:200]}")
        if res.pdf_path:
            print(f"    → {res.pdf_path}")
        if res.musicxml_path:
            print(f"    → {res.musicxml_path}")
    print()

    return 0


def main() -> int:
    """主入口 / Main entry point."""
    from src.config import setup_logging

    # 初始化日志 (CLI 模式: WARNING → 控制台, INFO → 文件)
    setup_logging(
        log_file=_PROJECT_ROOT / "logs" / "umuse.log",
        console_level=logging.WARNING,
    )

    parser = argparse.ArgumentParser(
        prog="umuse",
        description="UMuse — AI 音乐逆向工程工作站",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # === separate ===
    sep_parser = subparsers.add_parser("separate", help="音频分轨")
    sep_parser.add_argument("input", help="输入音频文件路径")
    sep_parser.add_argument("-o", "--output", help="输出目录")
    sep_parser.add_argument("-s", "--strategy", default="vocal_priority",
                           choices=["vocal_priority", "full_band"],
                           help="分轨策略: vocal_priority (Roformer人声 + Demucs乐器) "
                                "| full_band (仅Demucs 6轨)")
    sep_parser.add_argument("-d", "--device", default="auto",
                           choices=["auto", "cuda", "cpu"],
                           help="计算设备 (默认: auto)")
    sep_parser.add_argument("--shifts", type=int, default=1,
                           help="Shift 增强次数 (0=最快, 仅Demucs)")
    sep_parser.add_argument("--overlap", type=float, default=0.25,
                           help="重叠度 0-1 (仅Demucs)")
    sep_parser.add_argument("--mp3", action="store_true",
                           help="输出 MP3 格式")

    # === info ===
    info_parser = subparsers.add_parser("info", help="查看音频文件信息")
    info_parser.add_argument("input", help="音频文件路径")

    # === transcribe ===
    trans_parser = subparsers.add_parser("transcribe", help="MIDI 转录 (旋律乐器)")
    trans_parser.add_argument("stem", help="Stem 音频文件路径")
    trans_parser.add_argument("-o", "--output", help="输出目录")
    trans_parser.add_argument("--onset-threshold", type=float, default=0.5,
                             help="起音阈值 (默认: 0.5)")
    trans_parser.add_argument("--frame-threshold", type=float, default=0.3,
                             help="持续帧阈值 (默认: 0.3)")
    trans_parser.add_argument("--min-note-len", type=float, default=58.0,
                             help="最短音符长度 ms (默认: 58)")
    trans_parser.add_argument("--no-clean", action="store_true",
                             help="跳过 MIDI 后处理清洗")

    # === drums ===
    drum_parser = subparsers.add_parser("drums", help="鼓组采样切片")
    drum_parser.add_argument("stem", help="鼓组 stem 文件路径")
    drum_parser.add_argument("-o", "--output", help="输出目录")
    drum_parser.add_argument("--sensitivity", type=float, default=0.15,
                            help="检测灵敏度 0-1 (默认: 0.15, 越低越敏感)")
    drum_parser.add_argument("--top-n", type=int, default=8,
                            help="每种类型保留最佳切片数 (默认: 8)")

    # === pipeline ===
    pipe_parser = subparsers.add_parser("pipeline", help="运行完整流水线")
    pipe_parser.add_argument("input", help="输入音频文件路径")
    pipe_parser.add_argument("-o", "--output", help="输出目录")
    pipe_parser.add_argument("--no-transcribe", action="store_true",
                            help="跳过 MIDI 转录")
    pipe_parser.add_argument("--no-drums", action="store_true",
                            help="跳过鼓组切片")
    pipe_parser.add_argument("--no-notation", action="store_true",
                            help="跳过乐谱生成")
    pipe_parser.add_argument("--no-clean", action="store_true",
                            help="跳过 MIDI 清洗")
    pipe_parser.add_argument("--no-matching", action="store_true",
                            help="跳过音色匹配 (Phase 4)")
    pipe_parser.add_argument("--no-effects", action="store_true",
                            help="跳过效果器分析 (Phase 5)")
    pipe_parser.add_argument("--no-refinement", action="store_true",
                            help="跳过迭代精炼 (使用独立 Phase 4 + Phase 5)")
    pipe_parser.add_argument("--no-beat-analysis", action="store_true",
                            help="跳过节拍分析 (Phase 1.5, BPM/拍号/强拍检测)")

    # === match ===
    match_parser = subparsers.add_parser("match", help="音色预设匹配 (Phase 4)")
    match_parser.add_argument("stem", nargs="?", help="Stem 音频文件或项目目录 (--init-db 时可选)")
    match_parser.add_argument("-o", "--output", help="输出目录")
    match_parser.add_argument("-i", "--instrument", default=None,
                              help="限定乐器类型 (piano/guitar/bass/synth)")
    match_parser.add_argument("-k", "--top-k", type=int, default=5,
                              help="返回 Top-K 结果 (默认: 5)")
    match_parser.add_argument("--init-db", action="store_true",
                              help="首次运行: 初始化预设数据库")

    # === notation ===
    not_parser = subparsers.add_parser("notation", help="生成乐谱 (从 MIDI)")
    not_parser.add_argument("midi", help="MIDI 文件路径")
    not_parser.add_argument("-o", "--output", help="输出目录")
    not_parser.add_argument("-f", "--format", default="all",
                          choices=["staff", "jianpu", "tablature", "full_score", "all"],
                          help="谱式 (默认: all=全部)")
    not_parser.add_argument("-t", "--title", help="乐曲标题")
    not_parser.add_argument("--no-pdf", action="store_true",
                          help="跳过 PDF 编译 (仅输出 MusicXML/LilyPond)")

    # === effects ===
    effects_parser = subparsers.add_parser("effects", help="效果器参数预估 (Phase 5)")
    effects_parser.add_argument("input", help="Stem 音频文件或项目目录")
    effects_parser.add_argument("-o", "--output", help="输出目录")
    effects_parser.add_argument("-i", "--instrument", default=None,
                                help="乐器类型 (piano/guitar/bass/vocals)")
    effects_parser.add_argument("-p", "--preset", default=None,
                                help="匹配到的预设名 (单 stem 模式必需)")

    # === refine ===
    refine_parser = subparsers.add_parser("refine", help="音色精炼 (Phase 4→5→4 迭代)")
    refine_parser.add_argument("input", help="Stem 音频文件或项目目录")
    refine_parser.add_argument("-o", "--output", help="输出目录")
    refine_parser.add_argument("-i", "--instrument", default=None,
                               help="乐器类型 (piano/guitar/bass/vocals)")
    refine_parser.add_argument("--max-iter", type=int, default=3,
                               help="最大迭代次数 (默认: 3)")

    # === gui ===
    subparsers.add_parser("gui", help="启动 GUI 桌面应用")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "separate": cmd_separate,
        "info": cmd_info,
        "transcribe": cmd_transcribe,
        "drums": cmd_drums,
        "notation": cmd_notation,
        "pipeline": cmd_pipeline,
        "match": cmd_match,
        "effects": cmd_effects,
        "refine": cmd_refine,
        "gui": cmd_gui,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
