"""乐谱 Worker / Notation Worker.

在线程中执行乐谱生成。
"""

from __future__ import annotations

from src.gui.workers.base_worker import BaseWorker
from src.core.pipeline import PipelineManager


class NotationWorker(BaseWorker):
    """乐谱生成 Worker / Runs notation generation in background thread.

    用法:
        worker = NotationWorker(pipeline_manager, stem_name=None, fmt="staff", ...)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        pipeline_manager: PipelineManager,
        stem_name: str | None = None,
        notation_format: str = "staff",
        title: str | None = None,
        composer: str = "",
    ) -> None:
        super().__init__()
        self._pm = pipeline_manager
        self._stem_name = stem_name
        self._notation_format = notation_format
        self._title = title
        self._composer = composer

    def work(self) -> dict:
        """执行乐谱生成工作."""
        return self._pm.run_notation(
            stem_name=self._stem_name,
            notation_format=self._notation_format,
            title=self._title,
            composer=self._composer,
            progress_callback=self.report_progress,
        )

