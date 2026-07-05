"""效果器分析 Worker / Effects Analysis Worker.

在线程中执行 Phase 5 效果器分析 (独立模式或迭代精炼模式)。
"""

from __future__ import annotations

from src.gui.workers.base_worker import BaseWorker
from src.core.pipeline import PipelineManager


class EffectsWorker(BaseWorker):
    """效果器分析 Worker / Runs effects analysis in background thread.

    用法:
        worker = EffectsWorker(pipeline_manager, stem_name="piano", refine=True)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        pipeline_manager: PipelineManager,
        stem_name: str | None = None,
        use_refinement: bool = True,
        max_iterations: int = 3,
    ) -> None:
        super().__init__()
        self._pm = pipeline_manager
        self._stem_name = stem_name
        self._use_refinement = use_refinement
        self._max_iterations = max_iterations

    def work(self) -> dict:
        """执行效果器分析."""
        if self._use_refinement:
            # 迭代精炼: Phase 4→5→4
            from src.core.refinement import RefinementResult
            refinement_results = self._pm.run_refinement(
                stem_name=self._stem_name,
                max_iterations=self._max_iterations,
                progress_callback=self.report_progress,
            )
            # 转为可序列化的 dict
            return {
                "mode": "refinement",
                "results": {
                    name: r.to_dict() for name, r in refinement_results.items()
                },
            }
        else:
            # 独立效果器分析: Phase 5 only
            effects_results = self._pm.run_effects_analysis(
                stem_name=self._stem_name,
                progress_callback=self.report_progress,
            )
            return {
                "mode": "effects_only",
                "results": {
                    name: profile.to_dict()
                    for name, profile in effects_results.items()
                },
            }
