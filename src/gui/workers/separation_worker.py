"""分轨 Worker / Separation Worker.

在线程中执行音频分轨。
"""

from __future__ import annotations

from pathlib import Path

from src.gui.workers.base_worker import BaseWorker
from src.core.project import Project, ProjectStatus


class SeparationWorker(BaseWorker):
    """分轨 Worker / Runs stem separation in background thread.

    用法:
        worker = SeparationWorker(project, ...)
        worker.moveToThread(thread)
        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        project: Project,
        strategy: str = "vocal_priority",
        device: str = "auto",
        shifts: int = 1,
        overlap: float = 0.25,
        mp3: bool = False,
    ) -> None:
        super().__init__()
        self._project = project
        self._strategy = strategy
        self._device = device
        self._shifts = shifts
        self._overlap = overlap
        self._mp3 = mp3

    def work(self) -> dict[str, Path]:
        """执行分轨工作."""
        from src.core.separation.audio_separator_runner import StemSeparator

        if not self._project.input_file or not self._project.output_dir:
            raise ValueError("项目缺少 input_file 或 output_dir")

        self._project.set_status(ProjectStatus.SEPARATING)

        separator = StemSeparator(device=self._device)
        stems = separator.separate(
            input_path=self._project.input_file,
            output_dir=self._project.output_dir,
            strategy=self._strategy,
            shifts=self._shifts,
            overlap=self._overlap,
            mp3=self._mp3,
            progress_callback=self.report_progress,
        )

        # 更新 project
        for stem_name, stem_path in stems.items():
            if stem_name in self._project.stems:
                self._project.stems[stem_name].path = stem_path

        self._project.separation_model = "htdemucs_6s"
        self._project.set_status(ProjectStatus.SEPARATED)
        self._project.set_progress(100, "分轨完成")

        return stems

