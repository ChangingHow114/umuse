"""音色匹配 Worker / Timbre Matching Worker.

在线程中执行 Phase 4 音色预设匹配。
"""

from __future__ import annotations

from src.gui.workers.base_worker import BaseWorker
from src.core.pipeline import PipelineManager


class TimbreWorker(BaseWorker):
    """音色匹配 Worker / Runs timbre matching in background thread.

    用法:
        worker = TimbreWorker(pipeline_manager, "piano", top_k=5)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        pipeline_manager: PipelineManager,
        stem_name: str,
        top_k: int = 5,
    ) -> None:
        super().__init__()
        self._pm = pipeline_manager
        self._stem_name = stem_name
        self._top_k = top_k

    def work(self) -> dict[str, list[dict]]:
        """执行音色匹配."""
        return self._pm.run_timbre_matching(
            stem_name=self._stem_name,
            top_k=self._top_k,
            progress_callback=self.report_progress,
        )
