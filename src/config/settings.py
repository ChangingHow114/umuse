"""应用设置 / Application Settings.

可调参数集中管理。支持:
- YAML 配置文件加载/保存
- 环境变量覆盖 (UMUSE_ 前缀)
- 运行时修改并持久化

用法:
    from src.config.settings import Settings
    settings = Settings()
    settings.load()  # 从默认路径加载
    print(settings.sample_rate)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.config.constants import (
    APP_NAME,
    DEFAULT_SAMPLE_RATE,
    EQ_MAX_BANDS,
    FEATURE_VECTOR_DIM,
    MAX_AUDIO_DURATION_SEC,
    N_MFCC,
    PROJECT_ROOT,
    SUPPORTED_AUDIO_FORMATS,
)


@dataclass
class SeparationSettings:
    """分轨设置 / Separation settings."""

    strategy: str = "vocal_priority"  # 分轨策略: vocal_priority | full_band
    device: str = "auto"  # auto | cuda | cpu
    shifts: int = 1  # Demucs shift 增强 (越大越慢但质量越好, 0=禁用)
    overlap: float = 0.25  # 重叠度 (0=无重叠, 0.25=推荐)
    output_format: str = "wav"  # wav | flac | mp3
    mp3_bitrate: int = 320  # kbps (仅 mp3 格式)


@dataclass
class TranscriptionSettings:
    """MIDI 转录设置 / Transcription settings."""

    onset_threshold: float = 0.5  # 音符起始检测阈值 (0-1)
    frame_threshold: float = 0.3  # 音符持续检测阈值 (0-1)
    minimum_note_length: float = 0.03  # 最短音符 (秒)
    minimum_frequency: float = 32.7  # 最低频率 Hz (C1)
    maximum_frequency: float = 2093.0  # 最高频率 Hz (C7)
    melodia_trick: bool = True  # basic-pitch 的 melodia 技巧


@dataclass
class TimbreSettings:
    """音色匹配设置 / Timbre matching settings."""

    feature_dim: int = FEATURE_VECTOR_DIM
    n_mfcc: int = N_MFCC
    n_mfcc_delta: int = 2  # MFCC delta/delta-delta
    top_k: int = 5  # 返回的 Top-K 匹配结果数
    similarity_metric: str = "cosine"  # cosine | euclidean
    mfcc_weight: float = 0.5  # MFCC 特征权重
    spectral_weight: float = 0.3  # 频谱特征权重
    envelope_weight: float = 0.2  # 包络特征权重


@dataclass
class EffectsSettings:
    """效果器分析设置 / Effects analysis settings."""

    eq_bands: int = EQ_MAX_BANDS  # 拟合的 EQ 频段数
    eq_smooth_window: int = 11  # 频谱平滑窗口 (奇数)
    reverb_rt60_min: float = 0.1  # 最小 RT60 (秒)
    reverb_rt60_max: float = 10.0  # 最大 RT60 (秒)
    compression_search_iterations: int = 100  # 差分进化迭代次数
    # 迭代精炼设置
    refinement_max_iterations: int = 3  # 最大迭代次数
    refinement_convergence_threshold: float = 0.02  # 收敛阈值 (得分提升)
    dry_synthesis_duration_sec: float = 3.0  # 干音参考合成时长


@dataclass
class NotationSettings:
    """乐谱设置 / Notation settings."""

    lilypond_path: str = "lilypond"  # LilyPond 可执行文件路径或命令
    output_format: str = "pdf"  # pdf | png | musicxml
    paper_size: str = "a4"
    font_size: int = 20  # 五线谱字号 (pt)
    title: str = ""  # 标题 (空=自动生成)
    show_chord_names: bool = True  # 显示和弦名称
    tab_string_count: int = 6  # 六线谱弦数


@dataclass
class BeatDetectionSettings:
    """节拍检测设置 / Beat detection settings."""

    enabled: bool = True
    preferred_stem: str = "drums"  # 优先用于 BPM 检测的 stem
    sr: int = 22050  # 分析采样率
    bpm_min: float = 40.0
    bpm_max: float = 250.0
    downbeat_confidence_threshold: float = 0.3


@dataclass
class RhythmAnalysisSettings:
    """节奏分析设置 / Rhythm analysis settings."""

    enabled: bool = True
    min_pattern_occurrences: int = 2  # 模式出现 ≤ 此值 → 标记碎音
    short_note_threshold_ms: float = 150.0  # 碎音候选最大时值 (ms)
    section_review_interval_bars: int = 16  # 每 N 小节复核一次
    section_alignment_warning_pct: float = 0.3  # 偏离 > 此比例发出警告


@dataclass
class OctaveOptimizationSettings:
    """八度优化设置 / Octave optimization settings."""

    enabled: bool = True
    bass_8_clef: bool = True          # bass 用 bass_8 谱号
    guitar_8vb_clef: bool = True      # guitar 用 treble_8vb 谱号
    ottava_high_threshold: int = 79   # MIDI pitch (G5) — 高于此加 8va
    ottava_low_threshold: int = 48    # MIDI pitch (C3) — 低于此加 8vb
    ottava_min_measures: int = 2      # 最少连续小节数才加 ottava


@dataclass
class UISettings:
    """UI 设置 / UI settings."""

    theme: str = "dark_purple"  # dark_purple | light_purple
    language: str = "zh"  # zh | en
    window_width: int = 1280
    window_height: int = 800
    sidebar_width: int = 180
    show_waveform: bool = True
    show_spectrogram: bool = False
    auto_save: bool = True
    auto_save_interval_minutes: int = 5


@dataclass
class Settings:
    """应用设置主类 / Main settings container."""

    # 子设置
    separation: SeparationSettings = field(default_factory=SeparationSettings)
    transcription: TranscriptionSettings = field(default_factory=TranscriptionSettings)
    timbre: TimbreSettings = field(default_factory=TimbreSettings)
    effects: EffectsSettings = field(default_factory=EffectsSettings)
    notation: NotationSettings = field(default_factory=NotationSettings)
    beat_detection: BeatDetectionSettings = field(default_factory=BeatDetectionSettings)
    rhythm_analysis: RhythmAnalysisSettings = field(default_factory=RhythmAnalysisSettings)
    octave: OctaveOptimizationSettings = field(default_factory=OctaveOptimizationSettings)
    ui: UISettings = field(default_factory=UISettings)

    # 通用设置
    sample_rate: int = DEFAULT_SAMPLE_RATE
    max_duration_sec: float = MAX_AUDIO_DURATION_SEC
    supported_formats: tuple[str, ...] = SUPPORTED_AUDIO_FORMATS
    output_root: Path = PROJECT_ROOT / "output"
    temp_dir: Path = PROJECT_ROOT / "temp"
    models_dir: Path = PROJECT_ROOT / "assets" / "models"

    # 配置路径 (不持久化到 YAML)
    _config_path: Path | None = field(default=None, repr=False)

    # ===== YAML 序列化 =====

    def to_dict(self) -> dict[str, Any]:
        """转为字典 (用于 YAML 序列化)."""
        return {
            "sample_rate": self.sample_rate,
            "max_duration_sec": self.max_duration_sec,
            "output_root": str(self.output_root),
            "models_dir": str(self.models_dir),
            "separation": _dataclass_to_dict(self.separation),
            "transcription": _dataclass_to_dict(self.transcription),
            "timbre": _dataclass_to_dict(self.timbre),
            "effects": _dataclass_to_dict(self.effects),
            "notation": _dataclass_to_dict(self.notation),
            "beat_detection": _dataclass_to_dict(self.beat_detection),
            "rhythm_analysis": _dataclass_to_dict(self.rhythm_analysis),
            "octave": _dataclass_to_dict(self.octave),
            "ui": _dataclass_to_dict(self.ui),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """从字典创建 (用于 YAML 反序列化)."""
        settings = cls()
        if "sample_rate" in data:
            settings.sample_rate = int(data["sample_rate"])
        if "max_duration_sec" in data:
            settings.max_duration_sec = float(data["max_duration_sec"])
        if "output_root" in data:
            settings.output_root = Path(data["output_root"])
        if "models_dir" in data:
            settings.models_dir = Path(data["models_dir"])

        # 子设置合并
        for key, cls_type in [
            ("separation", SeparationSettings),
            ("transcription", TranscriptionSettings),
            ("timbre", TimbreSettings),
            ("effects", EffectsSettings),
            ("notation", NotationSettings),
            ("beat_detection", BeatDetectionSettings),
            ("rhythm_analysis", RhythmAnalysisSettings),
            ("octave", OctaveOptimizationSettings),
            ("ui", UISettings),
        ]:
            if key in data:
                merged = _dict_to_dataclass(data[key], getattr(settings, key))
                setattr(settings, key, merged)

        return settings

    # ===== 文件 I/O =====

    @classmethod
    def default_path(cls) -> Path:
        """获取默认配置文件路径."""
        return PROJECT_ROOT / "settings.yaml"

    def load(self, path: Path | None = None) -> "Settings":
        """从 YAML 文件加载设置, 使用环境变量覆盖."""
        config_path = path or self.default_path()
        self._config_path = config_path

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            loaded = self.from_dict(data)
            self._merge_from(loaded)

        # 环境变量覆盖 (UMUSE_ 前缀)
        self._apply_env_overrides()
        return self

    def save(self, path: Path | None = None) -> None:
        """保存设置到 YAML 文件."""
        save_path = path or self._config_path or self.default_path()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, default_flow_style=False)

    def _merge_from(self, other: "Settings") -> None:
        """合并另一个 Settings 实例的值."""
        for field_name in self.__dataclass_fields__:
            if field_name.startswith("_"):
                continue
            val = getattr(other, field_name)
            if val is not None:
                setattr(self, field_name, val)

    def _apply_env_overrides(self) -> None:
        """应用环境变量覆盖 (UMUSE_ 前缀)."""
        env_map = {
            "UMUSE_SAMPLE_RATE": ("sample_rate", int),
            "UMUSE_STRATEGY": ("separation.strategy", str),
            "UMUSE_DEVICE": ("separation.device", str),
            "UMUSE_THEME": ("ui.theme", str),
            "UMUSE_LANGUAGE": ("ui.language", str),
            "UMUSE_OUTPUT_ROOT": ("output_root", Path),
        }
        for env_key, (attr_path, converter) in env_map.items():
            env_val = os.environ.get(env_key)
            if env_val is not None:
                _set_nested_attr(self, attr_path, converter(env_val))


# ===== 辅助函数 =====

def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """将 dataclass 转换为 dict (递归)."""
    result = {}
    for f in obj.__dataclass_fields__:
        val = getattr(obj, f)
        if isinstance(val, Path):
            result[f] = str(val)
        elif hasattr(val, "__dataclass_fields__"):
            result[f] = _dataclass_to_dict(val)
        elif isinstance(val, tuple):
            result[f] = list(val)
        else:
            result[f] = val
    return result


def _dict_to_dataclass(data: dict[str, Any], existing: Any) -> Any:
    """将 dict 合并到现有 dataclass (只更新存在的字段)."""
    for key, val in data.items():
        if hasattr(existing, key):
            current = getattr(existing, key)
            if isinstance(current, Path) and isinstance(val, str):
                setattr(existing, key, Path(val))
            elif hasattr(current, "__dataclass_fields__") and isinstance(val, dict):
                setattr(existing, key, _dict_to_dataclass(val, current))
            else:
                setattr(existing, key, val)
    return existing


def _set_nested_attr(obj: Any, attr_path: str, value: Any) -> None:
    """设置嵌套属性, 如 'separation.model'. """
    parts = attr_path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)
