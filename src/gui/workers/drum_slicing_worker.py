"""鼓组切片 Worker / Drum Slicing Worker.

在线程中执行鼓组采样切片。
"""

from __future__ import annotations

from src.gui.workers.base_worker import BaseWorker
from src.core.pipeline import PipelineManager


class DrumSlicingWorker(BaseWorker):
    """鼓组切片 Worker / Runs drum sample slicing in background thread.

    用法:
        worker = DrumSlicingWorker(pipeline_manager)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        super().__init__()
        self._pm = pipeline_manager

    def work(self) -> dict:
        """执行鼓组切片工作."""
        return self._pm.run_drum_slicing(
            progress_callback=self.report_progress,
        )

