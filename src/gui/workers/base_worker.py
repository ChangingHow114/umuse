"""Worker 基类 / Base Worker QObject.

所有 Worker 继承此基类，通过信号与主线程通信。
Worker 从不直接操作 Widget。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class BaseWorker(QObject):
    """Worker 基类 / Base worker using QObject + signals.

    信号:
        started: 任务开始
        progress: 进度更新 (percent, message)
        finished: 任务完成 (result)
        error: 任务失败 (error_message)

    子类需实现:
        work() — 执行实际逻辑，返回结果
        run() — 调用 work() 并发射相应信号
    """

    started = Signal()
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        """执行任务 / Execute the task.

        子类可覆盖此方法以自定义信号发射顺序。
        默认实现:
            1. emit started()
            2. 调用 work()
            3. emit finished(result) 或 emit error(msg)
        """
        try:
            self.started.emit()
            result = self.work()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def work(self):
        """执行实际工作 / Do the actual work.

        子类必须覆盖此方法。
        """
        raise NotImplementedError("子类必须实现 work() 方法")

    def report_progress(self, pct: int, msg: str) -> None:
        """便捷方法: 发射进度信号 / Convenience: emit progress.

        Args:
            pct: 进度百分比 (0-100)
            msg: 进度描述
        """
        self.progress.emit(pct, msg)

