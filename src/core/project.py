"""项目管理 / Project Data Model.

Project 数据类追踪整个处理流程的状态和文件路径。
支持 JSON 序列化，可保存/恢复工作状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path


class ProjectStatus(Enum):
    """项目状态 / Project status."""

    CREATED = auto()       # 刚创建
    IMPORTING = auto()     # 导入音频中
    READY = auto()         # 就绪，等待处理
    SEPARATING = auto()    # 分轨中
    SEPARATED = auto()     # 分轨完成
    TRANSCRIBING = auto()  # 转录中
    TRANSCRIBED = auto()   # 转录完成
    MATCHING = auto()      # 音色匹配中
    MATCHED = auto()       # 音色匹配完成
    ESTIMATING = auto()    # 效果器分析中
    ESTIMATED = auto()     # 效果器分析完成
    NOTATING = auto()      # 乐谱生成中
    COMPLETED = auto()     # 全部完成
    FAILED = auto()        # 失败


@dataclass
class StemInfo:
    """单轨信息 / Stem info."""

    name: str                # 乐器名 (piano, drums, ...)
    name_zh: str             # 中文名 (钢琴, 鼓组, ...)
    path: Path | None = None              # stem 音频路径
    midi_path: Path | None = None         # MIDI 文件路径
    preset_matches_path: Path | None = None  # 预设匹配结果 JSON
    effects_params_path: Path | None = None  # 效果器参数 JSON
    sheet_paths: dict[str, Path] = field(default_factory=dict)  # 乐谱路径 {格式: 路径}
    sample_slices: list[Path] = field(default_factory=list)  # 采样切片 (鼓组/FX)
    is_melodic: bool = True   # 是否为旋律乐器

    # 运行时匹配结果 (不持久化到 project.json)
    matched_presets: list[dict] = field(default_factory=list, repr=False)
    top_preset: str | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """转为字典."""
        return {
            "name": self.name,
            "name_zh": self.name_zh,
            "path": str(self.path) if self.path else None,
            "midi_path": str(self.midi_path) if self.midi_path else None,
            "preset_matches_path": str(self.preset_matches_path) if self.preset_matches_path else None,
            "effects_params_path": str(self.effects_params_path) if self.effects_params_path else None,
            "sheet_paths": {k: str(v) for k, v in self.sheet_paths.items()},
            "sample_slices": [str(p) for p in self.sample_slices],
            "is_melodic": self.is_melodic,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StemInfo":
        """从字典恢复."""
        return cls(
            name=d["name"],
            name_zh=d.get("name_zh", d["name"]),
            path=Path(d["path"]) if d.get("path") else None,
            midi_path=Path(d["midi_path"]) if d.get("midi_path") else None,
            preset_matches_path=Path(d["preset_matches_path"]) if d.get("preset_matches_path") else None,
            effects_params_path=Path(d["effects_params_path"]) if d.get("effects_params_path") else None,
            sheet_paths={k: Path(v) for k, v in d.get("sheet_paths", {}).items()},
            sample_slices=[Path(p) for p in d.get("sample_slices", [])],
            is_melodic=d.get("is_melodic", True),
        )


@dataclass
class Project:
    """项目数据类 / Project data model.

    追踪整个 UMuse 处理流程的状态和输出文件。
    """

    # === 基本信息 ===
    name: str = "Untitled"
    input_file: Path | None = None
    output_dir: Path | None = None

    # === 状态 ===
    status: ProjectStatus = ProjectStatus.CREATED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # === 元数据 ===
    audio_duration_sec: float = 0.0
    audio_sample_rate: int = 44100
    audio_channels: int = 2

    # === 分轨结果 ===
    separation_model: str = "htdemucs_6s"
    stems: dict[str, StemInfo] = field(default_factory=dict)  # key=英文乐器名

    # === 进度信息 ===
    current_step: str = ""       # 当前步骤描述
    progress_percent: float = 0.0  # 当前步骤进度 0-100
    error_message: str = ""      # 错误信息

    def __post_init__(self):
        """初始化 stems 字典 (如果没有提供)."""
        if not self.stems:
            self._init_stems_from_model(self.separation_model)

    def _init_stems_from_model(self, model: str) -> None:
        """根据模型创建默认 StemInfo."""
        from src.config.constants import DEMUCS_6S_STEMS, MELODIC_INSTRUMENTS
        for eng_name, zh_name in DEMUCS_6S_STEMS.items():
            self.stems[eng_name] = StemInfo(
                name=eng_name,
                name_zh=zh_name,
                is_melodic=eng_name in MELODIC_INSTRUMENTS,
            )

    def get_melodic_stems(self) -> dict[str, StemInfo]:
        """获取旋律乐器 stems (需要 MIDI 转录的)."""
        return {k: v for k, v in self.stems.items() if v.is_melodic}

    def get_sample_stems(self) -> dict[str, StemInfo]:
        """获取采样类 stems (鼓组/FX, 不需要 MIDI 转录)."""
        return {k: v for k, v in self.stems.items() if not v.is_melodic}

    def set_status(self, status: ProjectStatus) -> None:
        """更新状态并自动更新时间戳."""
        self.status = status
        self.updated_at = datetime.now().isoformat()

    def set_progress(self, percent: float, step: str) -> None:
        """更新进度信息."""
        self.progress_percent = percent
        self.current_step = step
        self.updated_at = datetime.now().isoformat()

    # ===== 序列化 =====

    def to_dict(self) -> dict:
        """转为字典 (JSON 安全)."""
        return {
            "name": self.name,
            "input_file": str(self.input_file) if self.input_file else None,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "status": self.status.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "audio_duration_sec": self.audio_duration_sec,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
            "separation_model": self.separation_model,
            "stems": {k: v.to_dict() for k, v in self.stems.items()},
            "current_step": self.current_step,
            "progress_percent": self.progress_percent,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        """从字典恢复."""
        project = cls(
            name=d.get("name", "Untitled"),
            input_file=Path(d["input_file"]) if d.get("input_file") else None,
            output_dir=Path(d["output_dir"]) if d.get("output_dir") else None,
            status=ProjectStatus[d.get("status", "CREATED")],
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            audio_duration_sec=d.get("audio_duration_sec", 0.0),
            audio_sample_rate=d.get("audio_sample_rate", 44100),
            audio_channels=d.get("audio_channels", 2),
            separation_model=d.get("separation_model", "htdemucs_6s"),
            current_step=d.get("current_step", ""),
            progress_percent=d.get("progress_percent", 0.0),
            error_message=d.get("error_message", ""),
        )
        # 恢复 stems
        project.stems = {
            k: StemInfo.from_dict(v) for k, v in d.get("stems", {}).items()
        }
        return project

    def save(self, path: Path | None = None) -> Path:
        """保存项目到 JSON 文件."""
        save_path = path or (self.output_dir / "project.json" if self.output_dir else None)
        if save_path is None:
            raise ValueError("没有指定保存路径且 output_dir 未设置")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return save_path

    @classmethod
    def load(cls, path: Path) -> "Project":
        """从 JSON 文件加载项目."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ===== 便捷方法 =====

    def ensure_output_dir(self) -> Path:
        """确保输出目录存在."""
        if self.output_dir is None:
            raise ValueError("output_dir 未设置")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

    def get_stem_subdir(self, stem_name: str, subdir: str) -> Path:
        """获取 stem 的子目录 (自动创建).

        Args:
            stem_name: 乐器名
            subdir: 子目录名 (midi, sheets, presets, samples)
        """
        d = self.ensure_output_dir() / stem_name / subdir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def summary(self) -> str:
        """打印项目摘要 (调试用)."""
        lines = [
            f"Project: {self.name}",
            f"  Status: {self.status.name}",
            f"  Input: {self.input_file}",
            f"  Output: {self.output_dir}",
            f"  Duration: {self.audio_duration_sec:.1f}s",
            f"  Separation Model: {self.separation_model}",
            f"  Stems ({len(self.stems)}):",
        ]
        for stem in self.stems.values():
            has_midi = "[Y]" if stem.midi_path else "[N]"
            has_preset = "[Y]" if stem.preset_matches_path else "[N]"
            has_effects = "[Y]" if stem.effects_params_path else "[N]"
            is_melodic = "旋律" if stem.is_melodic else "采样"
            lines.append(
                f"    [{is_melodic}] {stem.name_zh} ({stem.name}) "
                f"| MIDI:{has_midi} | Preset:{has_preset} | Effects:{has_effects}"
            )
        return "\n".join(lines)
