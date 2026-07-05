"""预设数据库建库工具 / Preset Database Builder.

用法:
    # 初始化内置预设 (无参考音频, 生成合成特征)
    python scripts/build_preset_db.py --init

    # 从参考音频目录添加预设
    python scripts/build_preset_db.py --add-audio data/presets/audio/piano/ \\
        --category acoustic_piano --instrument piano

    # 列出所有预设
    python scripts/build_preset_db.py --list

    # 导出预设为 JSON
    python scripts/build_preset_db.py --export presets_export.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.timbre.preset_database import PresetDatabase, Preset
from src.core.timbre.feature_extractor import FeatureExtractor
from src.core.timbre.matcher import format_match_results


def cmd_init(args: argparse.Namespace) -> int:
    """初始化数据库 (内置预设)."""
    db = PresetDatabase()
    db._init_builtin_presets()
    db.save()
    print(f"已创建包含 {db.count} 个内置预设的数据库")
    print(f"保存到: {db.db_path}")
    print(f"\n预设列表:")
    for p in db.presets:
        print(f"  [{p.category}] {p.name} — {p.description[:40]}")
    return 0


def cmd_add_audio(args: argparse.Namespace) -> int:
    """从参考音频添加预设."""
    audio_dir = Path(args.add_audio)
    if not audio_dir.exists():
        print(f"[X] 目录不存在: {audio_dir}")
        return 1

    db = PresetDatabase()
    db.load()
    extractor = FeatureExtractor()

    audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.mp3"))
    if not audio_files:
        print(f"[X] 目录中没有 WAV/MP3 文件: {audio_dir}")
        return 1

    print(f"从 {audio_dir} 扫描到 {len(audio_files)} 个音频文件\n")

    for audio_file in audio_files:
        name = audio_file.stem
        print(f"  处理: {name}…", end=" ")

        try:
            features = extractor.extract(audio_file)
            preset = Preset(
                name=name,
                category=args.category or "synth_pad",
                instrument=args.instrument or "synth",
                description=args.description or name,
                tags=args.tags.split(",") if args.tags else [],
                features=features,
                reference_audio=str(audio_file.relative_to(Path.cwd())),
            )
            db.add_preset(preset)
            print(f"OK ({len(features)} dims)")
        except Exception as e:
            print(f"FAILED: {e}")
            continue

    db.save()
    print(f"\n数据库已更新: {db.count} 个预设")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出所有预设."""
    db = PresetDatabase()
    db.load()

    print(f"\n预设数据库 ({db.count} 个预设):\n")
    print(f"{'类别':<25} {'名称':<40} {'特征':<8}")
    print("-" * 75)
    for p in db.presets:
        has_f = "YES" if p.has_features() else "synth"
        print(f"{p.category:<25} {p.name:<40} {has_f:<8}")
    print()

    if args.verbose:
        for p in db.presets:
            print(f"\n  [{p.category}] {p.name}")
            print(f"    乐器: {p.instrument}")
            print(f"    描述: {p.description or '(无)'}")
            print(f"    标签: {', '.join(p.tags) if p.tags else '(无)'}")
            print(f"    参数: {p.params}")
            print(f"    特征: {'有' if p.has_features() else '合成'}")
            print(f"    参考音频: {p.reference_audio or '(无)'}")

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """导出为 JSON."""
    import json
    db = PresetDatabase()
    db.load()

    data = {
        "version": 1,
        "preset_count": db.count,
        "presets": [p.to_dict() for p in db.presets],
    }

    export_path = Path(args.export)
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"导出 {db.count} 个预设到: {export_path}")
    return 0


def main() -> int:
    """CLI 入口."""
    parser = argparse.ArgumentParser(
        prog="build_preset_db",
        description="UMuse 预设数据库建库工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # init
    p_init = subparsers.add_parser("--init", help="初始化内置预设")
    p_init.set_defaults(func=cmd_init)

    # add-audio
    p_add = subparsers.add_parser("--add-audio", help="从参考音频目录添加预设")
    p_add.add_argument("add_audio", help="参考音频目录路径")
    p_add.add_argument("--category", default="synth_pad", help="乐器类别")
    p_add.add_argument("--instrument", default="synth", help="乐器类型")
    p_add.add_argument("--description", default="", help="预设描述")
    p_add.add_argument("--tags", default="", help="标签 (逗号分隔)")

    # list
    p_list = subparsers.add_parser("--list", help="列出所有预设")
    p_list.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    p_list.set_defaults(func=cmd_list)

    # export
    p_export = subparsers.add_parser("--export", help="导出为 JSON")
    p_export.add_argument("export", help="导出文件路径")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
