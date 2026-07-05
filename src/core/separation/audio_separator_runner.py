"""基于 audio-separator 的多策略分轨引擎.

通过 audio-separator (UVR 生态) 调用多种模型，实现比单一 Demucs
更好的分轨质量。支持多模型串联策略。

策略:
- full_band: 仅 htdemucs_6s (兼容旧版行为)
- vocal_priority: BS-Roformer (人声 SDR 12.9) + htdemucs_6s (乐器)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Callable

from src.config.constants import DEMUCS_6S_STEMS, DEMUCS_4S_STEMS, ASSETS_DIR

# 抑制 audio_separator 内部的 tqdm 和日志噪音
os.environ.setdefault("TQDM_DISABLE", "1")
logging.getLogger("audio_separator").setLevel(logging.WARNING)
logging.getLogger("separator").setLevel(logging.WARNING)


class StemSeparator:
    """基于 audio-separator 的多策略分轨器.

    用法:
        sep = StemSeparator()
        stems = sep.separate("song.wav", "output/", strategy="vocal_priority")
        # stems = {"vocals": Path(...), "drums": Path(...), ...}
    """

    # === 策略定义 ===
    # 每个策略定义一串模型分离步骤
    # models: [(model_filename, {输出stem名 -> 目标stem名})]
    # priority: 当多个模型输出同一 stem 时，按此顺序取第一个

    STRATEGIES: dict[str, dict] = {
        "full_band": {
            "name": "全频段 (Demucs 6轨)",
            "description": "仅用 htdemucs_6s 一键分离 6 轨 (兼容旧版)",
            "models": [
                {
                    "filename": "htdemucs_6s.yaml",
                    "stems": {
                        "vocals": "vocals",
                        "drums": "drums",
                        "bass": "bass",
                        "guitar": "guitar",
                        "piano": "piano",
                        "other": "other",
                    },
                },
            ],
            "priority": ["vocals", "drums", "bass", "guitar", "piano", "other"],
        },
        "vocal_priority": {
            "name": "人声优先 (Roformer + Demucs)",
            "description": "BS-Roformer 高质量人声 (SDR 12.9) + Demucs 6轨乐器",
            "models": [
                {
                    "filename": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                    "stems": {
                        "vocals": "vocals",
                        "instrumental": None,  # 中间产物，不纳入最终结果
                    },
                },
                {
                    "filename": "htdemucs_6s.yaml",
                    "stems": {
                        "vocals": None,  # 被 Roformer 覆盖
                        "drums": "drums",
                        "bass": "bass",
                        "guitar": "guitar",
                        "piano": "piano",
                        "other": "other",
                    },
                },
            ],
            "priority": [
                "vocals",   # Roformer 优先
                "drums", "bass", "guitar", "piano", "other",  # Demucs 兜底
            ],
        },
    }

    # stem 名称标准化映射
    _STEM_ALIASES: dict[str, str] = {
        "vocal": "vocals",
        "voice": "vocals",
        "drum": "drums",
        "bass": "bass",
        "guitar": "guitar",
        "piano": "piano",
        "other": "other",
        "instrumental": "instrumental",
        "no_vocals": "instrumental",
        "inst": "instrumental",
    }

    def __init__(
        self,
        device: str = "auto",
        model_cache_dir: str | Path | None = None,
    ):
        """初始化分轨器.

        Args:
            device: 设备选择 ('auto' | 'cuda' | 'cpu')
            model_cache_dir: 模型下载缓存目录
        """
        self.device = device

        if model_cache_dir is None:
            model_cache_dir = ASSETS_DIR / "models"
        self.model_cache_dir = Path(model_cache_dir)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)

    def separate(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        strategy: str = "vocal_priority",
        shifts: int = 1,
        overlap: float = 0.25,
        mp3: bool = False,
        mp3_bitrate: int = 320,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Path]:
        """执行音频分轨 / Run stem separation.

        Args:
            input_path: 输入音频文件路径
            output_dir: 输出根目录
            strategy: 分轨策略 ('vocal_priority' | 'full_band')
            shifts: SHIFT 增强次数 (仅 Demucs 模型有效)
            overlap: 重叠度 0-1 (仅 Demucs 模型有效)
            mp3: 是否输出 MP3 格式
            mp3_bitrate: MP3 比特率
            progress_callback: 进度回调 (percent, message)

        Returns:
            {英文乐器名: stem 文件路径}

        Raises:
            FileNotFoundError: 输入文件不存在
            RuntimeError: 分轨执行失败
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if strategy not in self.STRATEGIES:
            raise ValueError(
                f"不支持的策略: {strategy}, "
                f"可用: {list(self.STRATEGIES.keys())}"
            )

        strategy_def = self.STRATEGIES[strategy]
        models = strategy_def["models"]
        priority = strategy_def["priority"]

        output_dir.mkdir(parents=True, exist_ok=True)

        # 收集所有模型的输出
        collected: dict[str, Path] = {}  # stem_name -> best file path

        total_models = len(models)
        for idx, model_cfg in enumerate(models):
            model_filename = model_cfg["filename"]
            stem_map: dict[str, str | None] = model_cfg["stems"]

            # 检查模型是否已下载
            model_path = self.model_cache_dir / model_filename
            need_download = not model_path.exists()

            # 进度: 下载 + 推理分段
            base_pct = int(idx / total_models * 100)
            model_label = self._model_label(model_filename)

            if progress_callback:
                if need_download:
                    progress_callback(
                        base_pct, f"下载模型 {model_label}..."
                    )
                else:
                    progress_callback(
                        base_pct, f"加载模型 {model_label}..."
                    )

            # 创建 separation session
            from audio_separator.separator import Separator

            sep = Separator(
                output_dir=str(output_dir),
                output_format="MP3" if mp3 else "WAV",
                model_file_dir=str(self.model_cache_dir),
                log_level=logging.WARNING,
            )

            # 加载模型
            sep.load_model(model_filename=model_filename)

            if progress_callback:
                progress_callback(base_pct, f"推理中 ({model_label})...")

            # 执行分离
            output_files = sep.separate(str(input_path))

            # 解析输出文件 → stem 名
            model_stems = self._parse_output_files(
                output_files, stem_map, output_dir
            )

            # 按优先级合并 (先到先得)
            for stem_name, file_path in model_stems.items():
                if stem_name not in collected:
                    collected[stem_name] = file_path

            if progress_callback:
                pct = int((idx + 1) / total_models * 95)
                progress_callback(pct, f"{model_label} 完成")

        # 按优先级排序，确保最终结果完整
        final_stems: dict[str, Path] = {}
        for stem_name in priority:
            if stem_name in collected and stem_name not in final_stems:
                final_stems[stem_name] = collected[stem_name]

        # 补充未在 priority 中的 stems
        for stem_name, file_path in collected.items():
            if stem_name not in final_stems:
                final_stems[stem_name] = file_path

        if not final_stems:
            raise RuntimeError(
                f"分轨未产生任何输出文件。"
                f"请检查 {output_dir} 目录"
            )

        if progress_callback:
            progress_callback(100, f"分轨完成! {len(final_stems)} 轨已分离")

        return final_stems

    def _parse_output_files(
        self,
        output_files: list[str],
        stem_map: dict[str, str | None],
        output_dir: Path,
    ) -> dict[str, Path]:
        """解析模型输出文件, 映射到标准 stem 名.

        audio-separator 的输出命名规则:
        - Demucs:    {song}_(StemName)_{model}.wav
        - Roformer:  {song}_(Vocals)_{model}.wav  /  {song}_(Instrumental)_{model}.wav
        - MDX:       {song}_(Vocals)_{model}.wav  /  {song}_(No Vocals)_{model}.wav

        Args:
            output_files: 输出文件路径列表 (可能是裸文件名或完整路径)
            stem_map: {输出stem关键词 -> 目标stem名, None表示跳过}
            output_dir: 模型输出目录 (用于解析相对路径)

        Returns:
            {标准stem名: Path}
        """
        result: dict[str, Path] = {}

        for filepath in output_files:
            fpath = Path(filepath)
            # 如果是裸文件名, 补全为完整路径
            if not fpath.is_absolute() and not fpath.exists():
                fpath = output_dir / fpath
            # 确保是绝对路径
            fpath = fpath.resolve()
            filename = fpath.stem  # 去掉扩展名

            # 尝试从文件名中提取 stem 类型
            # 格式: {song_name}_(StemType)_{model_name}
            # 用正则匹配 _(StemType)_ 部分
            match = re.search(r"_\(([^)]+)\)_", filename)
            if match:
                raw_stem = match.group(1).lower()
            else:
                # 退而求其次: 检查 filename 中包含的 stem 关键词
                raw_stem = filename.lower()

            # 标准化 stem 名
            stem_name = self._normalize_stem_name(raw_stem)

            if stem_name is None:
                continue

            # 检查 stem_map: 这个 stem 是否被需要
            if stem_name not in stem_map:
                # 检查是否通过 alias 映射
                continue

            mapped = stem_map[stem_name]
            if mapped is None:
                # 显式标记为不需要
                continue

            result[mapped] = fpath

        return result

    def _normalize_stem_name(self, raw: str) -> str | None:
        """标准化 stem 名称.

        Args:
            raw: 原始 stem 名 (可能来自文件名)

        Returns:
            标准化的 stem 名, 无法识别返回 None
        """
        raw = raw.strip().lower().replace(" ", "_")

        # 直接别名匹配
        if raw in self._STEM_ALIASES:
            return self._STEM_ALIASES[raw]

        # 检查是否为已知的 6-stem 名称
        if raw in DEMUCS_6S_STEMS:
            return raw

        # 检查 4-stem 名称
        if raw in DEMUCS_4S_STEMS:
            return raw

        # 子串模糊匹配 (处理 "no_vocals" → "instrumental" 等)
        for alias, target in self._STEM_ALIASES.items():
            if alias in raw:
                return target

        return None

    def _model_label(self, filename: str) -> str:
        """从文件名提取简短模型标识."""
        # model_bs_roformer_ep_317_sdr_12.9755.ckpt → Roformer
        # htdemucs_6s.yaml → Demucs-6s
        # MDX23C-DrumSep-aufr33-jarredou.ckpt → DrumSep
        name = filename.rsplit(".", 1)[0]  # 去扩展名
        if "roformer" in name.lower():
            if "drum" in name.lower():
                return "Roformer-Drums"
            return "Roformer"
        if "demucs" in name.lower():
            if "6s" in name:
                return "Demucs-6s"
            if "ft" in name:
                return "Demucs-ft"
            return "Demucs"
        if "drum" in name.lower():
            return "DrumSep"
        # 截断长名
        if len(name) > 25:
            return name[:22] + "..."
        return name

    # === 兼容旧接口 ===

    @staticmethod
    def get_stem_info(model: str = "htdemucs_6s") -> dict[str, str]:
        """获取模型对应的分轨乐器信息."""
        if "6s" in model:
            return dict(DEMUCS_6S_STEMS)
        return dict(DEMUCS_4S_STEMS)

    @classmethod
    def get_available_strategies(cls) -> dict[str, dict]:
        """获取可用策略列表."""
        return {
            k: {
                "name": v["name"],
                "description": v["description"],
            }
            for k, v in cls.STRATEGIES.items()
        }

    # === DrumSep 专用 (Phase 2.3 使用) ===

    def separate_drums(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Path:
        """使用 MDX23C-DrumSep 专用模型提取鼓组.

        Args:
            input_path: 音频文件 (通常是无鼓的混合轨)
            output_dir: 输出目录
            progress_callback: 进度回调

        Returns:
            鼓组音频文件路径
        """
        from audio_separator.separator import Separator

        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(0, "加载 MDX23C 鼓组分离模型...")

        sep = Separator(
            output_dir=str(output_dir),
            output_format="WAV",
            model_file_dir=str(self.model_cache_dir),
            log_level=logging.WARNING,
        )

        sep.load_model(model_filename="MDX23C-DrumSep-aufr33-jarredou.ckpt")

        if progress_callback:
            progress_callback(30, "鼓组分离中...")

        output_files = sep.separate(str(input_path))

        # 找到鼓组文件 (处理裸文件名)
        drums_path = None
        for f in output_files:
            fpath = Path(f)
            if not fpath.is_absolute() and not fpath.exists():
                fpath = output_dir / fpath
            fpath = fpath.resolve()
            if "drum" in fpath.stem.lower():
                drums_path = fpath
                break

        if drums_path is None and output_files:
            fpath = Path(output_files[0])
            if not fpath.is_absolute() and not fpath.exists():
                fpath = output_dir / fpath
            drums_path = fpath.resolve()

        if drums_path is None:
            raise RuntimeError("鼓组分离未产生输出")

        if progress_callback:
            progress_callback(100, "鼓组分离完成")

        return drums_path
