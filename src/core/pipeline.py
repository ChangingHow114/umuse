"""流程编排器 / Pipeline Manager.

编排完整的 UMuse 处理流程: 分轨 → 转录 → 乐谱 → 音色匹配 → 效果器分析。
每个阶段可独立运行，也可串联执行。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from src.config.settings import Settings
from src.core.project import Project, ProjectStatus

logger = logging.getLogger(__name__)


class PipelineManager:
    """流程编排器 / Pipeline orchestrator.

    用法:
        settings = Settings().load()
        project = Project(name="MySong", input_file=Path("song.mp3"))
        pm = PipelineManager(project, settings)
        pm.run_separation(progress_callback=my_callback)
    """

    def __init__(self, project: Project, settings: Settings | None = None):
        """初始化编排器.

        Args:
            project: 项目实例
            settings: 应用设置 (可选, 默认加载)
        """
        self.project = project
        self.settings = settings or Settings().load()

    @staticmethod
    def _report(
        callback: Callable[[int, str], None] | None,
        pct: int,
        msg: str,
    ) -> None:
        """安全的进度回调 / Safe progress callback."""
        if callback:
            try:
                callback(pct, msg)
            except Exception:
                pass

    # ===== Phase 1: 音频分轨 =====

    def run_separation(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Path]:
        """执行音频分轨 / Run stem separation.

        Args:
            progress_callback: 进度回调 (percent, message)

        Returns:
            {英文乐器名: stem 文件路径}
        """
        from src.core.separation.audio_separator_runner import StemSeparator

        if not self.project.input_file or not self.project.output_dir:
            raise ValueError("项目缺少 input_file 或 output_dir")

        sep_settings = self.settings.separation
        self.project.set_status(ProjectStatus.SEPARATING)

        separator = StemSeparator(device=sep_settings.device)
        stems = separator.separate(
            input_path=self.project.input_file,
            output_dir=self.project.output_dir,
            strategy=sep_settings.strategy,
            shifts=sep_settings.shifts,
            overlap=sep_settings.overlap,
            mp3=(sep_settings.output_format == "mp3"),
            mp3_bitrate=sep_settings.mp3_bitrate,
            progress_callback=progress_callback,
        )

        # 更新 project 状态
        for stem_name, stem_path in stems.items():
            if stem_name in self.project.stems:
                self.project.stems[stem_name].path = stem_path
            else:
                # 未知 stem — 按采样处理
                from src.config.constants import DEMUCS_6S_STEMS
                zh_name = DEMUCS_6S_STEMS.get(stem_name, stem_name)
                from src.core.project import StemInfo
                self.project.stems[stem_name] = StemInfo(
                    name=stem_name,
                    name_zh=zh_name,
                    path=stem_path,
                    is_melodic=False,
                )

        self.project.separation_model = "htdemucs_6s"  # 底层模型标识
        self.project.set_status(ProjectStatus.SEPARATED)
        self.project.set_progress(100, "分轨完成")

        return stems

    # ===== Phase 2: MIDI 转录 =====

    def run_transcription(
        self,
        stem_name: str | None = None,
        onset_threshold: float = 0.5,
        frame_threshold: float = 0.3,
        minimum_note_length: float = 58.0,
        clean_midi_output: bool = True,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, dict]:
        """执行 MIDI 转录 / Run MIDI transcription.

        对旋律乐器 stem 执行 basic-pitch ONNX 转录。
        鼓组/Other 走采样切片路径 (run_drum_slicing)。

        Args:
            stem_name: 指定 stem 名 (None=所有旋律乐器)
            onset_threshold: 起音阈值 (0-1)
            frame_threshold: 持续帧阈值 (0-1)
            minimum_note_length: 最短音符 (ms)
            clean_midi_output: 是否后处理清洗 MIDI
            progress_callback: 进度回调

        Returns:
            {stem_name: {
                'midi_path': Path, 'midi_data': PrettyMIDI,
                'note_count': int, 'clean_report': CleanReport | None
            }}
        """
        from src.core.transcription import transcribe, clean_midi, CleanConfig

        self.project.set_status(ProjectStatus.TRANSCRIBING)

        # 确定要转录的 stem: 只处理旋律乐器
        melodic_stems = ["piano", "guitar", "bass", "vocals"]
        if stem_name:
            if stem_name not in melodic_stems:
                raise ValueError(
                    f"不支持转录的乐器: {stem_name}。"
                    f"旋律乐器支持: {melodic_stems}"
                )
            target_stems = [stem_name]
        else:
            target_stems = [
                s for s in melodic_stems
                if s in self.project.stems and self.project.stems[s].path
            ]

        if not target_stems:
            raise ValueError("没有可转录的 stem。请先运行分轨。")

        results: dict[str, dict] = {}
        n_stems = len(target_stems)

        for i, sname in enumerate(target_stems):
            stem_path = self.project.stems[sname].path
            if not stem_path or not stem_path.exists():
                continue

            stage_base = i / n_stems * 100

            def stem_progress(pct: int, msg: str) -> None:
                total = int(stage_base + pct / n_stems)
                if progress_callback:
                    progress_callback(
                        total, f"[转录:{sname}] {msg} (stem {i+1}/{n_stems})"
                    )

            if progress_callback:
                progress_callback(
                    int(stage_base), f"转录 {sname} (第 {i+1}/{n_stems} 轨)..."
                )

            midi_dir = self.project.output_dir / "midi"
            midi_dir.mkdir(parents=True, exist_ok=True)

            result = transcribe(
                audio_path=stem_path,
                output_dir=midi_dir,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length=minimum_note_length,
                progress_callback=stem_progress,
            )

            clean_report = None
            if clean_midi_output and result["midi_data"] is not None:
                cleaned, clean_report = clean_midi(
                    result["midi_data"],
                    CleanConfig(merge_overlapping=True, normalize_velocity=True),
                    progress_callback=lambda p, m: stem_progress(85 + p // 7, m),
                )
                # 覆盖保存清洗后的 MIDI
                if result["midi_path"]:
                    cleaned_path = Path(result["midi_path"])
                    cleaned.write(str(cleaned_path))
                    result["midi_data"] = cleaned

            results[sname] = {
                "midi_path": result["midi_path"],
                "midi_data": result["midi_data"],
                "note_count": len(result["note_events"]),
                "note_events": result["note_events"],
                "clean_report": clean_report,
            }

            # 更新 project 状态
            if result["midi_path"]:
                self.project.stems[sname].midi_path = result["midi_path"]

        self.project.set_status(ProjectStatus.TRANSCRIBED)
        if progress_callback:
            total_notes = sum(r["note_count"] for r in results.values())
            progress_callback(100, f"转录完成: {n_stems} 轨, {total_notes} 个音符")

        return results

    # ===== Phase 2: 鼓组采样切片 =====

    def run_drum_slicing(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict:
        """对鼓组 stem 执行采样切片 / Run drum sample slicing.

        Returns:
            切片结果字典
        """
        from src.core.transcription import slice_drum_stem, export_drum_kit

        drum_stem = self.project.stems.get("drums")
        if not drum_stem or not drum_stem.path or not drum_stem.path.exists():
            raise ValueError("没有鼓组 stem。请先运行分轨。")

        slices_dir = self.project.output_dir / "slices" / "drums"

        result = slice_drum_stem(
            audio_path=drum_stem.path,
            output_dir=slices_dir,
            save_slices=True,
            save_by_type=True,
            progress_callback=progress_callback,
        )

        # 导出精选鼓组
        kit_dir = self.project.output_dir / "slices" / "drum_kit"
        kit = export_drum_kit(result, kit_dir)

        return {
            "slice_result": result,
            "drum_kit": kit,
            "output_dir": slices_dir,
        }

    # ===== Phase 3: 乐谱生成 =====

    def run_notation(
        self,
        stem_name: str | None = None,
        notation_format: str = "staff",
        title: str | None = None,
        composer: str = "",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict:
        """生成乐谱 / Generate sheet music.

        从转录好的 MIDI 文件生成乐谱（五线谱/简谱/六线谱/总谱）。

        Args:
            stem_name: 指定 stem (None=使用所有有 MIDI 的旋律 stem)
            notation_format: 谱式
                - 'staff' (五线谱)
                - 'jianpu' (简谱)
                - 'tablature' (六线谱, 需要 guitar/bass stem)
                - 'full_score' (总谱)
                - 'all' (全部格式)
            title: 乐曲标题 (None=使用项目名)
            composer: 作曲者
            progress_callback: 进度回调

        Returns:
            {
                'results': {NotationFormat: NotationResult},
                'output_dir': Path,
            }
        """
        from src.core.notation.midi_to_score import midi_to_score
        from src.core.notation.notation_formats import (
            NotationFormat, NotationResult,
            generate_staff, generate_jianpu, generate_tablature,
            generate_full_score, generate_all_formats,
        )
        from src.core.notation.lilypond_exporter import get_lilypond_path

        # 自动检测 LilyPond 路径 (跨平台)
        ly_path = get_lilypond_path()
        if ly_path.name == "lilypond" or ly_path.exists():
            pass  # PATH 查找或已找到，无需手动设置

        self.project.set_status(ProjectStatus.NOTATING)

        if title is None:
            title = self.project.name

        # Determine which stems to process
        melodic_stems = ["piano", "guitar", "bass", "vocals"]
        if stem_name:
            target_stems = [stem_name]
        else:
            target_stems = [
                s for s in melodic_stems
                if s in self.project.stems and self.project.stems[s].midi_path
            ]

        if not target_stems:
            raise ValueError(
                "没有可生成乐谱的 stem。请先运行 MIDI 转录 (run_transcription)。"
            )

        notation_dir = self.project.output_dir / "notation"
        notation_dir.mkdir(parents=True, exist_ok=True)

        # Load all MIDI → music21 Scores
        if progress_callback:
            progress_callback(5, "加载 MIDI 文件...")

        scores: dict[str, music21.stream.Score] = {}
        for i, sname in enumerate(target_stems):
            midi_path = self.project.stems[sname].midi_path
            if not midi_path or not midi_path.exists():
                continue
            scores[sname] = midi_to_score(
                midi_path,
                progress_callback=lambda p, m, sn=sname: (
                    progress_callback(5 + int(p * 0.25), f"加载 {sn}: {m}")
                    if progress_callback else None
                ),
            )

        if not scores:
            raise ValueError("无法加载任何 MIDI 文件。")

        if progress_callback:
            progress_callback(30, f"生成乐谱 ({notation_format})...")

        # Map format string to NotationFormat
        format_map = {
            "staff": NotationFormat.STAFF,
            "jianpu": NotationFormat.JIANPU,
            "tablature": NotationFormat.TABLATURE,
            "full_score": NotationFormat.FULL_SCORE,
            "all": None,  # special: generate all
        }
        fmt = format_map.get(notation_format)
        if fmt is None and notation_format != "all":
            raise ValueError(
                f"不支持的谱式: {notation_format}。"
                f"支持: staff, jianpu, tablature, full_score, all"
            )

        # Generate notation
        if notation_format == "all":
            results = generate_all_formats(
                scores, notation_dir, title=title, composer=composer,
                compile_pdf=True,
                progress_callback=progress_callback,
            )
        elif notation_format == "staff":
            first_score = next(iter(scores.values()))
            results = {
                NotationFormat.STAFF: generate_staff(
                    first_score, notation_dir, title=title, composer=composer,
                    compile_pdf=True, progress_callback=progress_callback,
                ),
            }
        elif notation_format == "jianpu":
            first_score = next(iter(scores.values()))
            results = {
                NotationFormat.JIANPU: generate_jianpu(
                    first_score, notation_dir, title=title,
                    compile_pdf=True, progress_callback=progress_callback,
                ),
            }
        elif notation_format == "tablature":
            tab_stem = scores.get("guitar") or scores.get("bass")
            if tab_stem is None:
                raise ValueError("六线谱需要 guitar 或 bass stem 的 MIDI 数据。")
            inst = "bass" if "bass" in scores else "guitar"
            results = {
                NotationFormat.TABLATURE: generate_tablature(
                    tab_stem, notation_dir, title=title, instrument_type=inst,
                    compile_pdf=True, progress_callback=progress_callback,
                ),
            }
        elif notation_format == "full_score":
            results = {
                NotationFormat.FULL_SCORE: generate_full_score(
                    scores, notation_dir, title=title, composer=composer,
                    compile_pdf=True, progress_callback=progress_callback,
                ),
            }

        self.project.set_status(ProjectStatus.COMPLETED)

        if progress_callback:
            progress_callback(100, "乐谱生成完成")

        return {
            "results": results,
            "output_dir": notation_dir,
        }

    # ===== Phase 4: 音色匹配 =====

    def run_timbre_matching(
        self,
        stem_name: str | None = None,
        top_k: int | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, list[dict]]:
        """音色预设匹配 / Run timbre matching.

        对旋律乐器 stem 提取音色特征, 匹配最佳预设。

        Args:
            stem_name: 指定 stem 名 (None=所有旋律乐器)
            top_k: 返回 Top-K 结果 (默认 5)
            progress_callback: 进度回调

        Returns:
            {stem_name: [{preset_name, category, score, rank, params, description, tags}, ...]}
        """
        from src.core.timbre import (
            FeatureExtractor, PresetDatabase, PresetMatcher,
        )

        self.project.set_status(ProjectStatus.MATCHING)

        # 确定目标 stems (仅旋律乐器)
        melodic_stems = ["piano", "guitar", "bass", "vocals"]
        if stem_name:
            if stem_name not in melodic_stems:
                raise ValueError(
                    f"不支持的乐器: {stem_name}。旋律乐器: {melodic_stems}"
                )
            target_stems = [stem_name]
        else:
            target_stems = [
                s for s in melodic_stems
                if s in self.project.stems and self.project.stems[s].path
            ]

        if not target_stems:
            raise ValueError("没有可匹配的 stem。请先运行分轨。")

        # 初始化组件
        db = PresetDatabase()
        db.load()
        extractor = FeatureExtractor()
        matcher = PresetMatcher(db, extractor, settings=self.settings.timbre)
        top_k = top_k or self.settings.timbre.top_k

        results: dict[str, list[dict]] = {}
        n_stems = len(target_stems)

        for i, sname in enumerate(target_stems):
            stem_path = self.project.stems[sname].path
            if not stem_path or not stem_path.exists():
                continue

            stage_base = i / n_stems * 100

            def stem_progress(pct: int, msg: str) -> None:
                total = int(stage_base + pct / n_stems)
                if progress_callback:
                    progress_callback(
                        total, f"[匹配:{sname}] {msg} (stem {i+1}/{n_stems})"
                    )

            if progress_callback:
                progress_callback(
                    int(stage_base),
                    f"音色匹配 {sname} (第 {i+1}/{n_stems} 轨)...",
                )

            match_results = matcher.match_from_audio(
                stem_path,
                top_k=top_k,
                instrument_filter=sname if sname != "vocals" else None,
                progress_callback=stem_progress,
            )

            results[sname] = [r.to_dict() for r in match_results]

            # 更新 Project 中的 stem 记录
            stem = self.project.stems[sname]
            stem.matched_presets = results[sname]
            if match_results:
                stem.top_preset = match_results[0].preset_name

        # 保存项目
        self.project.save(self.project.output_dir / "project.json")

        return results

    # ===== Phase 5: 效果器分析 + 迭代精炼 =====

    def run_effects_analysis(
        self,
        stem_name: str | None = None,
        preset_name: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, "EffectsProfile"]:
        """效果器参数预估 / Run effects analysis.

        对旋律乐器 stem, 基于 Phase 4 匹配到的预设估算效果器参数。

        Args:
            stem_name: 指定 stem (None=所有旋律乐器)
            preset_name: 指定预设名 (None=使用 Phase 4 匹配结果)
            progress_callback: 进度回调

        Returns:
            {stem_name: EffectsProfile}
        """
        from src.core.effects import EffectsChainBuilder
        from src.core.timbre import FeatureExtractor, PresetDatabase
        import json
        import librosa

        self.project.set_status(ProjectStatus.ESTIMATING)

        melodic_stems = ["piano", "guitar", "bass", "vocals"]
        if stem_name:
            if stem_name not in melodic_stems:
                raise ValueError(
                    f"不支持效果器分析的乐器: {stem_name}。"
                    f"旋律乐器: {melodic_stems}"
                )
            target_stems = [stem_name]
        else:
            target_stems = [
                s for s in melodic_stems
                if s in self.project.stems and self.project.stems[s].path
            ]

        if not target_stems:
            raise ValueError("没有可分析效果器的 stem。请先运行分轨和音色匹配。")

        db = PresetDatabase()
        db.load()
        extractor = FeatureExtractor()
        builder = EffectsChainBuilder(self.settings.effects)

        results: dict = {}
        n_stems = len(target_stems)

        for i, sname in enumerate(target_stems):
            stem_info = self.project.stems[sname]
            if not stem_info or not stem_info.path:
                continue

            stage_base = i / n_stems * 100

            def stem_progress(pct: int, msg: str) -> None:
                total = int(stage_base + pct / n_stems)
                if progress_callback:
                    progress_callback(
                        total, f"[效果器:{sname}] {msg} (stem {i+1}/{n_stems})"
                    )

            if progress_callback:
                progress_callback(
                    int(stage_base),
                    f"效果器分析 {sname} (第 {i+1}/{n_stems} 轨)...",
                )

            # 确定要使用的预设名
            preset_name_to_use = preset_name
            if not preset_name_to_use:
                if stem_info.top_preset:
                    preset_name_to_use = stem_info.top_preset
                elif stem_info.matched_presets:
                    preset_name_to_use = stem_info.matched_presets[0].get("preset_name", "")
                    if isinstance(stem_info.matched_presets[0], dict):
                        preset_name_to_use = stem_info.matched_presets[0].get("preset_name", "")
                    else:
                        preset_name_to_use = getattr(stem_info.matched_presets[0], "preset_name", "")

            if not preset_name_to_use:
                logger.warning(f"{sname}: 无匹配预设, 跳过效果器分析")
                continue

            preset = db.get_preset(preset_name_to_use)
            if preset is None:
                logger.warning(f"{sname}: 预设 '{preset_name_to_use}' 不存在, 跳过")
                continue

            # 加载湿音
            stem_progress(10, "加载音频…")
            wet_audio, sr = librosa.load(
                str(stem_info.path), sr=44100, mono=True
            )

            # 合成干音参考
            stem_progress(20, "合成干音参考…")
            duration = len(wet_audio) / sr
            dry_audio = builder.synthesize_dry_reference(
                preset, duration_sec=duration, sr=sr,
                progress_callback=lambda p, m: stem_progress(20 + p // 5, m),
            )

            # 估算效果器
            stem_progress(40, "估算 EQ/混响/压缩…")
            profile = builder.estimate_all(
                dry_audio, wet_audio, sr,
                stem_name=sname,
                preset_name=preset_name_to_use,
                progress_callback=lambda p, m: stem_progress(40 + p * 3 // 5, m),
            )
            results[sname] = profile

            # 保存效果器参数 JSON
            effects_dir = self.project.output_dir / sname
            effects_dir.mkdir(parents=True, exist_ok=True)
            effects_json_path = effects_dir / "effects_params.json"
            with open(effects_json_path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
            stem_info.effects_params_path = effects_json_path

        self.project.set_status(ProjectStatus.ESTIMATED)

        return results

    def run_refinement(
        self,
        stem_name: str | None = None,
        max_iterations: int = 3,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, "RefinementResult"]:
        """运行 Phase 4→5→4 迭代精炼 / Run Phase 4→5→4 refinement loop.

        Args:
            stem_name: 指定 stem (None=所有旋律乐器)
            max_iterations: 最大迭代次数
            progress_callback: 进度回调

        Returns:
            {stem_name: RefinementResult}
        """
        from src.core.timbre import (
            FeatureExtractor, PresetDatabase, PresetMatcher, FeatureCompensator,
        )
        from src.core.effects import EffectsChainBuilder
        from src.core.refinement import RefinementController, RefinementResult
        import json

        self.project.set_status(ProjectStatus.ESTIMATING)

        # 首先运行第一轮 Phase 4 匹配 (如果还没有匹配结果)
        melodic_stems = ["piano", "guitar", "bass", "vocals"]
        if stem_name:
            target_stems = [stem_name]
        else:
            target_stems = [
                s for s in melodic_stems
                if s in self.project.stems and self.project.stems[s].path
            ]

        # 检查哪些 stem 有匹配结果
        stems_without_matches = [
            s for s in target_stems
            if not self.project.stems[s].matched_presets
        ]
        if stems_without_matches:
            self._report(progress_callback, 0, "第一轮: 音色粗匹配…")
            self.run_timbre_matching(
                stem_name=None if len(stems_without_matches) > 1 else stems_without_matches[0],
                progress_callback=lambda p, m: self._report(
                    progress_callback, p // 10, f"[粗匹配] {m}"
                ),
            )

        # 初始化组件
        db = PresetDatabase()
        db.load()
        extractor = FeatureExtractor()
        matcher = PresetMatcher(db, extractor, settings=self.settings.timbre)
        builder = EffectsChainBuilder(self.settings.effects)
        compensator = FeatureCompensator()

        controller = RefinementController(
            matcher=matcher,
            chain_builder=builder,
            compensator=compensator,
            max_iterations=max_iterations,
            convergence_threshold=self.settings.effects.refinement_convergence_threshold,
        )

        results: dict[str, RefinementResult] = {}
        n_stems = len(target_stems)

        for i, sname in enumerate(target_stems):
            stem_info = self.project.stems[sname]
            if not stem_info.path:
                continue

            # 构建 MatchResult 对象
            from src.core.timbre.matcher import MatchResult
            preliminary = []
            for m in stem_info.matched_presets[:5]:
                preliminary.append(MatchResult(
                    preset_name=m.get("preset_name", ""),
                    category=m.get("category", ""),
                    instrument=m.get("instrument", ""),
                    score=m.get("score", 0.0),
                    rank=m.get("rank", 0),
                    params=m.get("params", {}),
                    description=m.get("description", ""),
                    tags=m.get("tags", []),
                ))

            if not preliminary:
                logger.warning(f"{sname}: 无匹配预设, 跳过精炼")
                continue

            stage_base = i / n_stems * 100

            def stem_progress(pct: int, msg: str) -> None:
                total = int(stage_base + pct / n_stems)
                if progress_callback:
                    progress_callback(
                        total, f"[精炼:{sname}] {msg} (stem {i+1}/{n_stems})"
                    )

            result = controller.refine(
                stem_audio_path=stem_info.path,
                stem_name=sname,
                preliminary_matches=preliminary,
                instrument_filter=sname if sname != "vocals" else None,
                top_k=self.settings.timbre.top_k,
                progress_callback=stem_progress,
            )
            results[sname] = result

            # 更新 project 中的 stem 记录
            stem_info.matched_presets = [m.to_dict() for m in result.refined_matches]
            if result.refined_matches:
                stem_info.top_preset = result.refined_matches[0].preset_name

            # 保存效果器参数
            if result.effects_profile:
                effects_dir = self.project.output_dir / sname
                effects_dir.mkdir(parents=True, exist_ok=True)
                effects_path = effects_dir / "effects_params.json"
                with open(effects_path, "w", encoding="utf-8") as f:
                    json.dump(result.effects_profile.to_dict(), f, ensure_ascii=False, indent=2)
                stem_info.effects_params_path = effects_path

        self.project.set_status(ProjectStatus.ESTIMATED)
        self.project.save(self.project.output_dir / "project.json")

        return results

    # ===== 完整流水线 =====

    def run_full_pipeline(
        self,
        skip_transcription: bool = False,
        skip_drum_slicing: bool = False,
        skip_notation: bool = False,
        skip_timbre: bool = False,
        skip_effects: bool = False,
        skip_refinement: bool = False,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Project:
        """执行完整流水线 / Run full pipeline end-to-end.

        Args:
            skip_transcription: 跳过 MIDI 转录
            skip_drum_slicing: 跳过鼓组切片
            skip_notation: 跳过乐谱生成
            skip_timbre: 跳过音色匹配 (Phase 4)
            skip_effects: 跳过效果器分析 (Phase 5 standalone)
            skip_refinement: 跳过迭代精炼 (Phase 4→5→4)
            progress_callback: 总进度回调 (percent, message)

        Returns:
            处理完成的 Project
        """
        stages = [
            ("分轨", self.run_separation),
        ]
        if not skip_transcription:
            stages.append(("MIDI 转录", self.run_transcription))
        if not skip_drum_slicing:
            stages.append(("鼓组切片", self.run_drum_slicing))
        if not skip_notation:
            stages.append(("乐谱生成", lambda **kw: self.run_notation(**kw)))
        if not skip_refinement and not skip_timbre:
            # 迭代精炼 (Phase 4→5→4 一体化)
            stages.append(("音色匹配+效果器", lambda **kw: self.run_refinement(**kw)))
        elif not skip_timbre:
            stages.append(("音色匹配", lambda **kw: self.run_timbre_matching(**kw)))
        if not skip_effects and skip_refinement:
            # 独立效果器分析 (不迭代)
            stages.append(("效果器分析", lambda **kw: self.run_effects_analysis(**kw)))

        for i, (stage_name, stage_func) in enumerate(stages):
            stage_pct_base = i / len(stages) * 100

            def stage_callback(pct: int, msg: str) -> None:
                """将阶段内进度映射到总进度."""
                total_pct = int(stage_pct_base + pct / len(stages))
                if progress_callback:
                    progress_callback(total_pct, f"[{stage_name}] {msg}")

            try:
                stage_func(progress_callback=stage_callback)
            except Exception as e:
                self.project.set_status(ProjectStatus.FAILED)
                self.project.error_message = f"{stage_name} 失败: {e}"
                raise

        self.project.set_status(ProjectStatus.COMPLETED)
        if progress_callback:
            progress_callback(100, "全部完成!")

        return self.project
