"""迭代精炼控制器 / Iterative Refinement Controller.

编排 Phase 4 (音色匹配) 和 Phase 5 (效果器估算) 的迭代优化循环,
通过特征补偿打破"湿音 vs 干音预设"的循环依赖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import librosa

from src.config.settings import Settings, EffectsSettings, TimbreSettings
from src.core.effects.types import EffectsProfile
from src.core.effects.chain_builder import EffectsChainBuilder
from src.core.timbre.feature_extractor import FeatureExtractor
from src.core.timbre.feature_compensator import FeatureCompensator
from src.core.timbre.preset_database import PresetDatabase, Preset
from src.core.timbre.matcher import PresetMatcher, MatchResult

logger = logging.getLogger(__name__)


# ===== 精炼结果 =====

@dataclass
class RefinementResult:
    """迭代精炼结果 / Refinement result for a single stem.

    Attributes:
        stem_name: 乐器名
        initial_matches: 第一轮 (粗)匹配结果
        refined_matches: 最终 (精)匹配结果
        effects_profile: 估算的效果器参数
        iterations: 实际迭代次数
        converged: 是否收敛
        score_improvement: 得分提升 (精匹配 vs 粗匹配)
        score_history: 各轮得分记录
        preset_history: 各轮 Top-1 预设名记录
    """

    stem_name: str
    initial_matches: list[MatchResult] = field(default_factory=list)
    refined_matches: list[MatchResult] = field(default_factory=list)
    effects_profile: EffectsProfile | None = None
    iterations: int = 0
    converged: bool = False
    score_improvement: float = 0.0
    score_history: list[float] = field(default_factory=list)
    preset_history: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """生成摘要字符串 / Generate summary string."""
        lines = [
            f"Refinement: {self.stem_name}",
            f"  Iterations: {self.iterations}, Converged: {self.converged}",
            f"  Score: {self.score_history[0]:.4f} → {self.score_history[-1]:.4f} "
            f"(Δ={self.score_improvement:+.4f})" if self.score_history else "  No scores",
            f"  Presets: {' → '.join(self.preset_history)}" if self.preset_history else "",
            f"  Initial Top-1: {self.initial_matches[0].preset_name if self.initial_matches else 'N/A'}",
            f"  Refined Top-1: {self.refined_matches[0].preset_name if self.refined_matches else 'N/A'}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """转为字典 / Convert to dict for JSON serialization."""
        return {
            "stem_name": self.stem_name,
            "initial_matches": [m.to_dict() for m in self.initial_matches],
            "refined_matches": [m.to_dict() for m in self.refined_matches],
            "effects_profile": self.effects_profile.to_dict() if self.effects_profile else None,
            "iterations": self.iterations,
            "converged": self.converged,
            "score_improvement": round(self.score_improvement, 4),
            "score_history": [round(s, 4) for s in self.score_history],
            "preset_history": self.preset_history,
        }


# ===== 精炼控制器 =====

class RefinementController:
    """迭代精炼控制器 / Iterative refinement controller.

    编排 Phase 4 (音色匹配) → Phase 5 (效果器估算) → 特征补偿 →
    重新 Phase 4 的迭代循环, 直到收敛或达到最大迭代次数。

    用法:
        db = PresetDatabase().load()
        matcher = PresetMatcher(db, FeatureExtractor())
        builder = EffectsChainBuilder()
        compensator = FeatureCompensator()

        controller = RefinementController(matcher, builder, compensator)
        result = controller.refine(stem_path, "piano", initial_matches)
    """

    def __init__(
        self,
        matcher: PresetMatcher,
        chain_builder: EffectsChainBuilder,
        compensator: FeatureCompensator,
        max_iterations: int = 3,
        convergence_threshold: float = 0.02,
        settings: Settings | None = None,
    ):
        """初始化精炼控制器.

        Args:
            matcher: 预设匹配器
            chain_builder: 效果器链构建器
            compensator: 特征补偿器
            max_iterations: 最大迭代次数
            convergence_threshold: 收敛阈值 (score 提升低于此值则停止)
            settings: 全局设置
        """
        self.matcher = matcher
        self.chain_builder = chain_builder
        self.compensator = compensator
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.settings = settings or Settings()
        self.extractor = FeatureExtractor()

    # ===== 主接口 =====

    def refine(
        self,
        stem_audio_path: Path,
        stem_name: str,
        preliminary_matches: list[MatchResult],
        instrument_filter: str | None = None,
        top_k: int = 5,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> RefinementResult:
        """运行迭代精炼 / Run iterative refinement.

        Args:
            stem_audio_path: stem 音频文件路径
            stem_name: 乐器名
            preliminary_matches: Phase 4 第一轮匹配结果
            instrument_filter: 乐器类型过滤 (如 "piano")
            top_k: 返回 Top-K 结果数
            progress_callback: 进度回调

        Returns:
            RefinementResult
        """
        if not preliminary_matches or not stem_audio_path.exists():
            return RefinementResult(
                stem_name=stem_name,
                initial_matches=preliminary_matches,
                refined_matches=preliminary_matches,
                iterations=0,
                converged=False,
            )

        score_history = [preliminary_matches[0].score]
        preset_history = [preliminary_matches[0].preset_name]
        best_matches = preliminary_matches
        best_effects: EffectsProfile | None = None

        current_preset_name = preliminary_matches[0].preset_name
        current_preset = self.matcher.database.get_preset(current_preset_name)
        if current_preset is None:
            return RefinementResult(
                stem_name=stem_name,
                initial_matches=preliminary_matches,
                refined_matches=preliminary_matches,
                iterations=0,
                converged=False,
            )

        # 加载湿音 (只加载一次)
        self._report(progress_callback, 0, f"加载音频: {stem_name}…")
        wet_audio, sr = librosa.load(str(stem_audio_path), sr=44100, mono=True)
        wet_features = self.extractor.extract_from_array(wet_audio, sr)

        converged = False
        final_iteration = 0

        for iteration in range(self.max_iterations):
            final_iteration = iteration + 1
            iter_base = iteration / self.max_iterations * 100

            self._report(
                progress_callback,
                int(iter_base),
                f"迭代 {iteration + 1}/{self.max_iterations}: {stem_name}",
            )

            # --- Phase 5: 估算效果器 ---
            self._report(
                progress_callback,
                int(iter_base + 5),
                f"合成干音参考 (preset={current_preset_name})…",
            )

            duration = len(wet_audio) / sr
            dry_audio = self.chain_builder.synthesize_dry_reference(
                current_preset,
                duration_sec=duration,
                sr=sr,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(iter_base + 5 + p / 3 * 20),
                    f"[合成] {m}",
                ),
            )

            effects = self.chain_builder.estimate_all(
                dry_audio, wet_audio, sr,
                stem_name=stem_name,
                preset_name=current_preset_name,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(iter_base + 25 + p / 3 * 50),
                    f"[效果器] {m}",
                ),
            )
            best_effects = effects

            # --- 特征补偿 ---
            self._report(progress_callback, int(iter_base + 75), "特征补偿…")
            compensated = self.compensator.compensate(
                wet_features, effects,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(iter_base + 75 + p / 3 * 10),
                    f"[补偿] {m}",
                ),
            )

            # --- 重新 Phase 4 ---
            self._report(progress_callback, int(iter_base + 85), "重新匹配…")
            new_matches = self.matcher.match(
                compensated,
                top_k=top_k,
                instrument_filter=instrument_filter,
                progress_callback=lambda p, m: self._report(
                    progress_callback,
                    int(iter_base + 85 + p / 3 * 15),
                    f"[匹配] {m}",
                ),
            )

            if not new_matches:
                logger.warning(f"迭代 {iteration+1}: 无匹配结果, 停止")
                break

            new_preset_name = new_matches[0].preset_name
            new_score = new_matches[0].score

            score_history.append(new_score)
            preset_history.append(new_preset_name)
            best_matches = new_matches

            # --- 检查收敛 ---
            if new_preset_name == current_preset_name:
                # 预设名不变 → 收敛
                logger.info(
                    f"迭代 {iteration+1}: 预设名不变 ({new_preset_name}), 收敛"
                )
                converged = True
                break

            score_improvement = new_score - score_history[-2]
            if score_improvement < self.convergence_threshold:
                # 得分提升不足 → 收敛
                logger.info(
                    f"迭代 {iteration+1}: 得分提升 {score_improvement:.4f} < "
                    f"{self.convergence_threshold}, 收敛"
                )
                converged = True
                break

            # 更新当前预设, 准备下一轮
            current_preset_name = new_preset_name
            current_preset = self.matcher.database.get_preset(new_preset_name)
            if current_preset is None:
                break

        # 计算最终得分提升
        final_score_improvement = score_history[-1] - score_history[0] if len(score_history) > 1 else 0.0

        self._report(progress_callback, 100, f"精炼完成: {stem_name} ({final_iteration} 轮)")

        return RefinementResult(
            stem_name=stem_name,
            initial_matches=preliminary_matches,
            refined_matches=best_matches,
            effects_profile=best_effects,
            iterations=final_iteration,
            converged=converged,
            score_improvement=final_score_improvement,
            score_history=score_history,
            preset_history=preset_history,
        )

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
                logger.debug("进度回调异常 (忽略)", exc_info=True)


def format_refinement_results(results: dict[str, RefinementResult]) -> str:
    """格式化所有 stem 的精炼结果 / Format refinement results for all stems.

    Args:
        results: {stem_name: RefinementResult}

    Returns:
        格式化的多行字符串
    """
    if not results:
        return "  (无精炼结果)"

    lines = [f"\n{'='*60}", "  Phase 4→5 Refinement Results", f"{'='*60}"]

    for sname, result in results.items():
        lines.append(f"\n  [{sname}]")
        lines.append(f"    Iterations: {result.iterations}, Converged: {result.converged}")

        if result.score_history:
            scores_str = " → ".join(f"{s:.4f}" for s in result.score_history)
            lines.append(f"    Scores: {scores_str} (Δ={result.score_improvement:+.4f})")

        if result.preset_history:
            presets_str = " → ".join(result.preset_history)
            lines.append(f"    Presets: {presets_str}")

        if result.effects_profile:
            lines.append(f"    Effects Confidence: {result.effects_profile.confidence:.2f}")

        # 最终匹配结果
        if result.refined_matches:
            lines.append(f"    Final Matches:")
            for m in result.refined_matches[:3]:
                lines.append(f"      #{m.rank} {m.preset_name} (score={m.score:.4f})")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)
