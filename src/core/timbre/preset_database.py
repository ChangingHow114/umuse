"""音色预设数据库 / Preset Database.

存储和管理音源预设, 支持:
- YAML 文件持久化
- 预设特征向量存储
- 用户自定义预设添加
- 内置参考预设 (无音频文件时提供 baseline)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

from src.config.constants import PRESETS_DIR, PRESET_CATEGORIES, FEATURE_VECTOR_DIM

logger = logging.getLogger(__name__)


# ===== 数据类 =====

@dataclass
class Preset:
    """单个音色预设 / A single timbre preset.

    Attributes:
        name: 预设名称 (如 "Grand Piano - Concert")
        category: 乐器类别 (如 "acoustic_piano")
        instrument: 目标乐器类型 (piano/guitar/bass/synth)
        description: 中文描述
        tags: 搜索标签
        features: 特征向量 (59-dim) — 可选, 有参考音频时自动提取
        params: DAW 参数建议 (如 attack/release/brightness)
        reference_audio: 参考音频路径 (可选)
    """

    name: str
    category: str = "synth_pad"
    instrument: str = "piano"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    features: np.ndarray | None = None
    params: dict[str, float] = field(default_factory=dict)
    reference_audio: str = ""  # 相对于 presets/audio/ 的路径

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化字典 (features 不序列化到 YAML)."""
        d = {
            "name": self.name,
            "category": self.category,
            "instrument": self.instrument,
            "description": self.description,
            "tags": self.tags,
            "params": self.params,
            "reference_audio": self.reference_audio,
        }
        if self.features is not None:
            d["features"] = self.features.tolist()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preset":
        """从字典创建预设."""
        features = None
        if "features" in data and data["features"] is not None:
            features = np.array(data["features"], dtype=np.float32)

        return cls(
            name=data.get("name", "Unnamed"),
            category=data.get("category", "synth_pad"),
            instrument=data.get("instrument", "piano"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            features=features,
            params=data.get("params", {}),
            reference_audio=data.get("reference_audio", ""),
        )

    def has_features(self) -> bool:
        """是否包含特征向量."""
        return self.features is not None and len(self.features) > 0

    def __repr__(self) -> str:
        return f"Preset({self.name!r}, cat={self.category}, has_features={self.has_features()})"


# ===== 数据库类 =====

class PresetDatabase:
    """预设数据库管理器 / Preset database manager.

    用法:
        db = PresetDatabase()
        db.load()  # 从默认路径加载
        presets = db.query(category="acoustic_piano")
        db.add_preset(preset)
        db.save()
    """

    # 默认数据库文件路径
    DEFAULT_DB_PATH: Path = PRESETS_DIR / "presets.yaml"
    DEFAULT_FEATURES_PATH: Path = PRESETS_DIR / "preset_features.npz"

    def __init__(self, db_path: Path | None = None):
        """初始化数据库.

        Args:
            db_path: YAML 数据库文件路径 (默认 data/presets/presets.yaml)
        """
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.features_path = self.db_path.with_suffix("").with_name(
            self.db_path.stem + "_features.npz"
        )
        self._presets: dict[str, Preset] = {}  # name → Preset

    # ===== 文件 I/O =====

    def load(self, path: Path | None = None) -> "PresetDatabase":
        """从 YAML 文件加载预设数据库.

        Args:
            path: 数据库文件路径 (可选, 默认 self.db_path)
        """
        load_path = path or self.db_path
        if not load_path.exists():
            logger.info(f"预设数据库文件不存在, 创建空数据库: {load_path}")
            self._init_builtin_presets()
            return self

        with open(load_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        presets_list = data.get("presets", [])
        for pdata in presets_list:
            preset = Preset.from_dict(pdata)
            self._presets[preset.name] = preset

        logger.info(f"加载了 {len(self._presets)} 个预设")

        # 如果有 .npz 特征文件, 加载特征
        self._load_features()

        return self

    def save(self, path: Path | None = None) -> None:
        """保存预设数据库到 YAML 文件.

        Args:
            path: 保存路径 (可选, 默认 self.db_path)
        """
        save_path = path or self.db_path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "preset_count": len(self._presets),
            "presets": [p.to_dict() for p in self._presets.values()],
        }

        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # 同时保存特征向量到 .npz (高效存储)
        self._save_features()

        logger.info(f"保存了 {len(self._presets)} 个预设到 {save_path}")

    def _save_features(self) -> None:
        """保存所有特征向量到 .npz 文件."""
        feature_dict = {}
        for name, preset in self._presets.items():
            if preset.has_features():
                feature_dict[name] = preset.features

        if feature_dict:
            np.savez_compressed(self.features_path, **feature_dict)
            logger.debug(f"保存了 {len(feature_dict)} 个特征向量到 {self.features_path}")

    def _load_features(self) -> None:
        """从 .npz 文件加载特征向量."""
        if not self.features_path.exists():
            return

        try:
            data = np.load(self.features_path, allow_pickle=False)
            for name in data.files:
                if name in self._presets:
                    self._presets[name].features = data[name]
            logger.debug(f"从 {self.features_path} 加载了 {len(data.files)} 个特征向量")
        except Exception as e:
            logger.warning(f"特征文件读取失败: {e}")

    # ===== 预设管理 =====

    def add_preset(self, preset: Preset) -> None:
        """添加或更新预设 / Add or update a preset.

        Args:
            preset: 预设对象
        """
        if not preset.name:
            raise ValueError("预设名称不能为空")
        self._presets[preset.name] = preset
        logger.info(f"添加预设: {preset.name}")

    def remove_preset(self, name: str) -> bool:
        """删除预设 / Remove a preset.

        Returns:
            True 如果删除成功, False 如果不存在
        """
        if name in self._presets:
            del self._presets[name]
            logger.info(f"删除预设: {name}")
            return True
        return False

    def get_preset(self, name: str) -> Preset | None:
        """按名称获取预设."""
        return self._presets.get(name)

    def query(
        self,
        category: str | None = None,
        instrument: str | None = None,
        tag: str | None = None,
    ) -> list[Preset]:
        """按条件筛选预设 / Query presets by criteria.

        Args:
            category: 乐器类别 (如 "acoustic_piano", 为 None 时不筛选)
            instrument: 乐器类型 (如 "piano", 为 None 时不筛选)
            tag: 标签搜索 (模糊匹配, 为 None 时不筛选)

        Returns:
            匹配的预设列表
        """
        results = list(self._presets.values())

        if category:
            results = [p for p in results if p.category == category]
        if instrument:
            results = [p for p in results if p.instrument == instrument]
        if tag:
            tag_lower = tag.lower()
            results = [p for p in results
                       if any(tag_lower in t.lower() for t in p.tags)]

        return results

    def get_feature_matrix(self) -> tuple[np.ndarray, list[str]]:
        """获取所有有特征的预设的特征矩阵 / Get feature matrix and names.

        Returns:
            (feature_matrix (N, dim), preset_names [N])
        """
        names = []
        features = []

        for name, preset in self._presets.items():
            if preset.has_features():
                names.append(name)
                features.append(preset.features)

        if not features:
            return np.array([]).reshape(0, FEATURE_VECTOR_DIM), []

        return np.stack(features), names

    # ===== 属性 =====

    @property
    def presets(self) -> list[Preset]:
        """所有预设列表."""
        return list(self._presets.values())

    @property
    def count(self) -> int:
        """预设数量."""
        return len(self._presets)

    @property
    def categories(self) -> list[str]:
        """所有类别列表."""
        return sorted(set(p.category for p in self._presets.values()))

    # ===== 内置预设 =====

    def _init_builtin_presets(self) -> None:
        """初始化内置参考预设 / Initialize built-in reference presets.

        这些是不依赖音频文件的"知识驱动"预设, 提供 baseline 匹配能力。
        用户可以通过添加参考音频来替换/增强这些预设的特征向量。
        """
        builtins = [
            # === 钢琴类 ===
            Preset(
                name="Grand Piano - Concert Bright",
                category="acoustic_piano", instrument="piano",
                description="明亮的大三角钢琴, 适合古典/独奏",
                tags=["钢琴", "三角钢琴", "bright", "classical", "concert"],
                params={"brightness": 0.75, "warmth": 0.40, "attack": 0.30, "sustain": 0.70, "body": 0.60},
            ),
            Preset(
                name="Grand Piano - Warm Jazz",
                category="acoustic_piano", instrument="piano",
                description="温暖的爵士钢琴, 中低频饱满",
                tags=["钢琴", "爵士", "warm", "jazz", "mellow"],
                params={"brightness": 0.35, "warmth": 0.75, "attack": 0.40, "sustain": 0.55, "body": 0.70},
            ),
            Preset(
                name="Electric Piano - Rhodes Classic",
                category="electric_piano", instrument="piano",
                description="经典 Rhodes 电钢琴, 铃铛般的音头",
                tags=["电钢琴", "rhodes", "bell", "vintage", "soul"],
                params={"brightness": 0.55, "warmth": 0.55, "attack": 0.45, "sustain": 0.60, "body": 0.50},
            ),
            Preset(
                name="Electric Piano - Wurlitzer",
                category="electric_piano", instrument="piano",
                description="Wurlitzer 电钢琴, 更有颗粒感",
                tags=["电钢琴", "wurlitzer", "gritty", "bark", "retro"],
                params={"brightness": 0.60, "warmth": 0.45, "attack": 0.55, "sustain": 0.50, "body": 0.55},
            ),
            Preset(
                name="Organ - Hammond B3 Clean",
                category="organ", instrument="piano",
                description="Hammond B3 风琴, 清澈音色",
                tags=["风琴", "hammond", "clean", "gospel", "rock"],
                params={"brightness": 0.50, "warmth": 0.50, "attack": 0.20, "sustain": 0.80, "body": 0.65},
            ),

            # === 吉他类 ===
            Preset(
                name="Acoustic Guitar - Steel String Bright",
                category="acoustic_guitar", instrument="guitar",
                description="明亮的钢弦原声吉他, 适合流行/民谣",
                tags=["原声吉他", "钢弦", "bright", "folk", "pop", "fingerstyle"],
                params={"brightness": 0.70, "warmth": 0.35, "attack": 0.65, "sustain": 0.40, "body": 0.50},
            ),
            Preset(
                name="Acoustic Guitar - Nylon Mellow",
                category="acoustic_guitar", instrument="guitar",
                description="温暖的尼龙弦古典吉他",
                tags=["古典吉他", "尼龙弦", "mellow", "classical", "fingerstyle"],
                params={"brightness": 0.30, "warmth": 0.70, "attack": 0.35, "sustain": 0.55, "body": 0.60},
            ),
            Preset(
                name="Electric Guitar - Clean Tube Amp",
                category="clean_guitar", instrument="guitar",
                description="干净的电子管音箱清音, 轻微压缩感",
                tags=["电吉他", "清音", "clean", "tube", "blues", "pop"],
                params={"brightness": 0.55, "warmth": 0.50, "attack": 0.60, "sustain": 0.50, "body": 0.50},
            ),
            Preset(
                name="Electric Guitar - Classic Rock Overdrive",
                category="distorted_guitar", instrument="guitar",
                description="经典摇滚过载音色, 中频突出",
                tags=["电吉他", "过载", "rock", "overdrive", "crunch", "blues"],
                params={"brightness": 0.50, "warmth": 0.40, "attack": 0.60, "sustain": 0.70, "body": 0.55},
            ),
            Preset(
                name="Electric Guitar - High Gain Metal",
                category="distorted_guitar", instrument="guitar",
                description="高增益金属音色, 低频紧实",
                tags=["电吉他", "金属", "high gain", "metal", "distortion", "heavy"],
                params={"brightness": 0.65, "warmth": 0.30, "attack": 0.70, "sustain": 0.85, "body": 0.70},
            ),

            # === 贝斯类 ===
            Preset(
                name="Bass - Fingerstyle Round",
                category="bass_guitar", instrument="bass",
                description="手指弹奏贝斯, 圆润温暖",
                tags=["贝斯", "指弹", "round", "warm", "fingerstyle", "r&b"],
                params={"brightness": 0.30, "warmth": 0.70, "attack": 0.35, "sustain": 0.60, "body": 0.75},
            ),
            Preset(
                name="Bass - Slap Funk",
                category="bass_guitar", instrument="bass",
                description="Slap 贝斯, 高频明亮有冲击力",
                tags=["贝斯", "slap", "funk", "bright", "percussive", "pop"],
                params={"brightness": 0.75, "warmth": 0.25, "attack": 0.80, "sustain": 0.30, "body": 0.55},
            ),
            Preset(
                name="Bass - Synth Deep Sub",
                category="synth_bass", instrument="bass",
                description="深沉的合成器低音, 808 风格",
                tags=["合成器贝斯", "808", "sub", "deep", "trap", "electronic"],
                params={"brightness": 0.15, "warmth": 0.85, "attack": 0.40, "sustain": 0.65, "body": 0.95},
            ),
            Preset(
                name="Bass - Pick P-Bass Rock",
                category="bass_guitar", instrument="bass",
                description="拨片弹 P-Bass, 经典摇滚贝斯音色",
                tags=["贝斯", "拨片", "p-bass", "rock", "pick", "driving"],
                params={"brightness": 0.45, "warmth": 0.50, "attack": 0.65, "sustain": 0.50, "body": 0.65},
            ),

            # === 合成器类 ===
            Preset(
                name="Synth Lead - Saw Wave Bright",
                category="synth_lead", instrument="synth",
                description="明亮的锯齿波主音, EDM/Pop",
                tags=["合成器", "lead", "saw", "bright", "edm", "pop"],
                params={"brightness": 0.80, "warmth": 0.20, "attack": 0.25, "sustain": 0.75, "body": 0.45},
            ),
            Preset(
                name="Synth Pad - Warm Analog Strings",
                category="synth_pad", instrument="synth",
                description="温暖的模拟合成器铺底",
                tags=["合成器", "pad", "analog", "warm", "strings", "ambient"],
                params={"brightness": 0.25, "warmth": 0.80, "attack": 0.50, "sustain": 0.75, "body": 0.60},
            ),
            Preset(
                name="Synth - Pluck FM Bell",
                category="synth_lead", instrument="synth",
                description="FM 合成器钟声拨弦音色",
                tags=["合成器", "pluck", "fm", "bell", "digital", "pop"],
                params={"brightness": 0.70, "warmth": 0.25, "attack": 0.10, "sustain": 0.35, "body": 0.35},
            ),

            # === 弦乐/管乐 ===
            Preset(
                name="Strings - Orchestral Section",
                category="strings", instrument="synth",
                description="管弦乐弦乐组, 柔美饱满",
                tags=["弦乐", "orchestral", "strings", "legato", "cinematic", "classical"],
                params={"brightness": 0.40, "warmth": 0.65, "attack": 0.55, "sustain": 0.70, "body": 0.60},
            ),
            Preset(
                name="Brass - Pop Horn Section",
                category="brass", instrument="synth",
                description="流行铜管组, 明亮有力",
                tags=["铜管", "brass", "horns", "pop", "bright", "punchy"],
                params={"brightness": 0.75, "warmth": 0.35, "attack": 0.60, "sustain": 0.45, "body": 0.60},
            ),
            Preset(
                name="Woodwinds - Flute Legato",
                category="woodwinds", instrument="synth",
                description="长笛连奏, 气息感强",
                tags=["木管", "长笛", "flute", "legato", "breathy", "soft"],
                params={"brightness": 0.55, "warmth": 0.45, "attack": 0.40, "sustain": 0.65, "body": 0.35},
            ),
        ]

        for preset in builtins:
            self._presets[preset.name] = preset

        logger.info(f"初始化了 {len(builtins)} 个内置预设 (无特征向量, 需参考音频)")
