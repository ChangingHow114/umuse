"""转录 Worker / Transcription Worker.

在线程中执行 MIDI 转录。
"""

from __future__ import annotations

from src.gui.workers.base_worker import BaseWorker
from src.core.pipeline import PipelineManager


class TranscriptionWorker(BaseWorker):
    """转录 Worker / Runs MIDI transcription in background thread.

    用法:
        worker = TranscriptionWorker(pipeline_manager, "piano", ...)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
    """

    def __init__(
        self,
        pipeline_manager: PipelineManager,
        stem_name: str,
        onset_threshold: float = 0.5,
        frame_threshold: float = 0.3,
        minimum_note_length: float = 58.0,
        clean_midi_output: bool = True,
    ) -> None:
        super().__init__()
        self._pm = pipeline_manager
        self._stem_name = stem_name
        self._onset_threshold = onset_threshold
        self._frame_threshold = frame_threshold
        self._minimum_note_length = minimum_note_length
        self._clean_midi_output = clean_midi_output

    def work(self) -> dict[str, dict]:
        """执行转录工作."""
        return self._pm.run_transcription(
            stem_name=self._stem_name,
            onset_threshold=self._onset_threshold,
            frame_threshold=self._frame_threshold,
            minimum_note_length=self._minimum_note_length,
            clean_midi_output=self._clean_midi_output,
            progress_callback=self.report_progress,
        )

