"""音色匹配器 / Timbre Preset Matcher.

使用 k-NN 搜索, 对输入的音频特征向量匹配最相近的音源预设。
支持:
- 余弦相似度 / 欧几里得距离
- 加权特征比较 (MFCC / 频谱 / 包络)
- 参数推断生成合成特征 (对无参考音频的预设)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from src.config.constants import N_MFCC, FEATURE_VECTOR_DIM
from src.config.settings import TimbreSettings
from src.core.timbre.feature_extractor import (
    FeatureExtractor,
    compare_features,
    compare_features_euclidean,
)
from src.core.timbre.preset_database import Preset, PresetDatabase

logger = logging.getLogger(__name__)


# ===== 匹配结果 =====

@dataclass
class MatchResult:
    """单个匹配结果 / A single match result.

    Attributes:
        preset_name: 预设名称
        category: 乐器类别
        instrument: 目标乐器
        score: 匹配得分 (0-1, 越高越好)
        rank: 排名 (1=最佳)
        params: 推荐 DAW 参数 (brightness/warmth/attack/sustain/body)
        synth_params: 合成器/插件参数 (Serum/Vital/General MIDI)
        description: 预设描述
        tags: 预设标签
    """

    preset_name: str
    category: str
    instrument: str
    score: float
    rank: int
    params: dict[str, float] = field(default_factory=dict)
    synth_params: dict[str, dict] = field(default_factory=dict)
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转为字典 (用于 JSON 序列化)."""
        return {
            "preset_name": self.preset_name,
            "category": self.category,
            "instrument": self.instrument,
            "score": round(self.score, 4),
            "rank": self.rank,
            "params": self.params,
            "synth_params": self.synth_params,
            "description": self.description,
            "tags": self.tags,
        }

    def __repr__(self) -> str:
        return (
            f"#{self.rank} {self.preset_name} "
            f"({self.category}, score={self.score:.3f})"
        )


# ===== 匹配器 =====

class PresetMatcher:
    """音色预设匹配器 / Timbre preset matcher.

    使用 k-NN 搜索, 从预设数据库中找到最佳匹配。

    用法:
        db = PresetDatabase().load()
        extractor = FeatureExtractor()
        matcher = PresetMatcher(db, extractor)

        features = extractor.extract("piano_stem.wav")
        results = matcher.match(features, top_k=5)
        # → [MatchResult, ...]
    """

    def __init__(
        self,
        database: PresetDatabase,
        extractor: FeatureExtractor | None = None,
        settings: TimbreSettings | None = None,
    ):
        """初始化匹配器.

        Args:
            database: 预设数据库
            extractor: 特征提取器 (用于合成特征)
            settings: 音色匹配设置
        """
        self.database = database
        self.extractor = extractor or FeatureExtractor()
        self.settings = settings or TimbreSettings()

    # ===== 主接口 =====

    def match(
        self,
        query_features: np.ndarray,
        top_k: int | None = None,
        instrument_filter: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> list[MatchResult]:
        """匹配最佳预设 / Match best presets for query features.

        Args:
            query_features: 查询特征向量 (feature_dim,)
            instrument_filter: 限定乐器类型 (如 "piano", None=不限)
            top_k: 返回数量 (默认使用 settings.top_k)
            progress_callback: 进度回调

        Returns:
            排序后的匹配结果列表
        """
        if top_k is None:
            top_k = self.settings.top_k

        query_features = np.asarray(query_features, dtype=np.float64)

        # 确保所有预设都有特征向量 (为内置预设生成合成特征)
        self._ensure_features(progress_callback)

        # 获取特征矩阵
        self._report(progress_callback, 20, "加载预设特征…")
        feature_matrix, preset_names = self.database.get_feature_matrix()

        if len(preset_names) == 0:
            logger.warning("没有可用的预设特征向量, 返回空结果")
            return []

        self._report(progress_callback, 40, "计算相似度…")
        similarity_fn = (
            compare_features
            if self.settings.similarity_metric == "cosine"
            else compare_features_euclidean
        )

        scores = []
        for i, name in enumerate(preset_names):
            preset = self.database.get_preset(name)
            if preset is None:
                continue

            # 乐器过滤
            if instrument_filter and preset.instrument != instrument_filter:
                continue

            preset_features = feature_matrix[i]
            sim = similarity_fn(query_features, preset_features)

            # 欧几里得距离需要反转为相似度
            if self.settings.similarity_metric == "euclidean":
                sim = 1.0 - sim

            scores.append((preset, sim))

        self._report(progress_callback, 70, "排序匹配结果…")

        # 按得分降序排列
        scores.sort(key=lambda x: x[1], reverse=True)

        # 构建结果 + 生成合成器参数
        from src.core.timbre.synth_params import SynthParamMapper
        mapper = SynthParamMapper()

        results = []
        for rank, (preset, score) in enumerate(scores[:top_k], start=1):
            # 从 preset.params 提取 high-level 参数 (有默认值)
            p = preset.params
            b = p.get("brightness", 0.5)
            w = p.get("warmth", 0.5)
            a = p.get("attack", 0.5)
            s = p.get("sustain", 0.5)
            bd = p.get("body", 0.5)

            synth_params = mapper.generate_all(
                brightness=b, warmth=w, attack=a, sustain=s, body=bd,
                instrument=preset.instrument,
            )

            results.append(MatchResult(
                preset_name=preset.name,
                category=preset.category,
                instrument=preset.instrument,
                score=float(score),
                rank=rank,
                params=preset.params,
                synth_params=synth_params,
                description=preset.description,
                tags=preset.tags,
            ))

        self._report(progress_callback, 100, "匹配完成")
        return results

    def match_from_audio(
        self,
        audio_path: str | Path,
        top_k: int | None = None,
        instrument_filter: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> list[MatchResult]:
        """从音频文件直接匹配 / Match directly from audio file.

        提取特征 → 匹配预设, 一步完成。

        Args:
            audio_path: 音频文件路径
            instrument_filter: 乐器类型过滤
            top_k: 返回数量
            progress_callback: 进度回调

        Returns:
            匹配结果列表
        """
        from pathlib import Path

        self._report(progress_callback, 0, "提取音频特征…")
        features = self.extractor.extract(Path(audio_path))

        self._report(progress_callback, 30, "搜索匹配预设…")
        return self.match(
            features,
            top_k=top_k,
            instrument_filter=instrument_filter,
            progress_callback=progress_callback,
        )

    # ===== 合成特征生成 =====

    def _ensure_features(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> None:
        """确保所有预设都有特征向量 / Ensure all presets have feature vectors.

        对于缺少特征向量的预设, 从其 params 参数推断合成特征。
        """
        missing = [p for p in self.database.presets if not p.has_features()]
        if not missing:
            return

        self._report(progress_callback, 10, f"生成合成特征 ({len(missing)} 个预设)…")
        for preset in missing:
            preset.features = self._synthesize_features(preset)

    def _synthesize_features(self, preset: Preset) -> np.ndarray:
        """从预设参数推断合成特征向量 / Synthesize feature vector from preset params.

        这是一个启发式映射, 用于在无参考音频时提供 baseline 匹配。
        参数含义:
          - brightness: 0-1, MFCC 高频系数, spectral centroid
          - warmth: 0-1, MFCC 低频系数, spectral rolloff (反向)
          - attack: 0-1, RMS 上升速度, onset strength
          - sustain: 0-1, RMS 均值
          - body: 0-1, 频谱带宽、谱对比度

        Args:
            preset: 预设对象 (必须包含 params)

        Returns:
            合成特征向量 (feature_dim,)
        """
        params = preset.params
        # 使用默认值填充缺失参数
        brightness = params.get("brightness", 0.5)
        warmth = params.get("warmth", 0.5)
        attack = params.get("attack", 0.5)
        sustain = params.get("sustain", 0.5)
        body = params.get("body", 0.5)

        dim = FEATURE_VECTOR_DIM
        vec = np.zeros(dim, dtype=np.float32)

        # Feature layout (59-dim):
        #   [0:20]   MFCC mean (20)
        #   [20:40]  MFCC std  (20)
        #   [40]     Spectral centroid
        #   [41]     Spectral bandwidth
        #   [42]     Spectral rolloff
        #   [43:50]  Spectral contrast (7)
        #   [50]     Zero-crossing rate
        #   [51]     RMS mean
        #   [52]     RMS std
        #   [53:59]  Chroma reduced (6)

        # --- MFCC mean (20): 模拟频谱包络 ---
        # 低频 MFCC (0-5): 受 warmth 和 body 影响
        for i in range(6):
            vec[i] = warmth * 1.2 + body * 0.5 + np.random.normal(0, 0.05)
        # 中频 MFCC (6-14): 受 brightness 和 body 影响
        for i in range(6, 15):
            vec[i] = brightness * 0.8 + body * 0.6 + np.random.normal(0, 0.05)
        # 高频 MFCC (15-19): 受 brightness 影响
        for i in range(15, 20):
            vec[i] = brightness * 1.0 + np.random.normal(0, 0.08)

        # --- MFCC std (20-39): 受 attack 影响 ---
        # attack 高 → MFCC 变化大
        for i in range(20, 40):
            vec[i] = attack * 0.6 + sustain * 0.3 + np.random.normal(0, 0.04)

        # --- Spectral centroid (40): 受 brightness 主导 ---
        vec[40] = brightness * 0.9 + warmth * 0.3 + np.random.normal(0, 0.03)

        # --- Spectral bandwidth (41): 受 body 和 sustain 影响 ---
        vec[41] = body * 0.8 + sustain * 0.4 + np.random.normal(0, 0.04)

        # --- Spectral rolloff (42): 受 brightness 主导 ---
        vec[42] = brightness * 0.85 + body * 0.3 + np.random.normal(0, 0.03)

        # --- Spectral contrast (43-49): 各频段峰值-谷值比 ---
        # 7 个频段: body 影响低中频, brightness 影响中高频
        for i in range(7):
            frac = i / 6.0  # 0 (低频段) → 1 (高频段)
            vec[43 + i] = body * (1.0 - frac) * 0.7 + brightness * frac * 0.8
            vec[43 + i] += np.random.normal(0, 0.05)

        # --- Zero-crossing rate (50): 受 brightness 影响 ---
        vec[50] = brightness * 0.7 + np.random.normal(0, 0.05)

        # --- RMS mean (51): 受 sustain 和 body 影响 ---
        vec[51] = sustain * 0.8 + body * 0.5 + np.random.normal(0, 0.03)

        # --- RMS std (52): 受 attack 影响 ---
        vec[52] = attack * 0.7 + np.random.normal(0, 0.05)

        # --- Chroma reduced (53-58): 受 instrument 类别影响 ---
        # 不同乐器有不同的泛音分布, 简化为色调偏移
        chroma_offset = {
            "piano": 0.0,
            "guitar": 0.15,
            "bass": -0.2,
            "synth": 0.1,
        }.get(preset.instrument, 0.0)

        for i in range(6):
            vec[53 + i] = 0.5 + chroma_offset + brightness * 0.3
            vec[53 + i] += np.random.normal(0, 0.08)

        # 归一化到 [0, 1] 范围
        vec = np.clip(vec, 0.0, 2.0)

        # 规范化: 使合成特征与真实特征的尺度大致对齐
        vec = vec / (np.linalg.norm(vec) + 1e-8) * 2.5

        return vec.astype(np.float32)

    # ===== 辅助 =====

    @staticmethod
    def _report(
        callback: Callable[[int, str], None] | None,
        pct: int,
        msg: str,
    ) -> None:
        """安全的进度回调."""
        if callback:
            try:
                callback(pct, msg)
            except Exception:
                logging.getLogger(__name__).debug(
                    "匹配器进度回调异常 (忽略)", exc_info=True,
                )


def format_match_results(results: list[MatchResult]) -> str:
    """格式化匹配结果为可读字符串 / Format match results as readable string.

    Args:
        results: 匹配结果列表

    Returns:
        格式化的多行字符串
    """
    if not results:
        return "  (无匹配结果)"

    lines = []
    for r in results:
        score_bar = "█" * int(r.score * 20) + "░" * (20 - int(r.score * 20))
        lines.append(
            f"  #{r.rank:<2} [{score_bar}] {r.score:.3f}  "
            f"{r.preset_name} ({r.category})"
        )
        if r.description:
            lines.append(f"      {r.description}")
        if r.params:
            params_str = ", ".join(
                f"{k}={v:.2f}" for k, v in list(r.params.items())[:5]
            )
            lines.append(f"      Params: {params_str}")
    return "\n".join(lines)
