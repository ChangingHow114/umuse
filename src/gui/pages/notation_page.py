"""乐谱页面 / Notation Page.

选择谱式和 stem，生成五线谱/简谱/六线谱/总谱。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QGroupBox,
    QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

if TYPE_CHECKING:
    from src.gui.windows.main_window import MainWindow

NOTATION_FORMATS = ["staff", "jianpu", "tablature", "full_score", "all"]
NOTATION_ZH = {
    "staff": "五线谱",
    "jianpu": "简谱",
    "tablature": "六线谱 (吉他/贝斯)",
    "full_score": "总谱 (全部乐器)",
    "all": "全部格式",
}


class NotationPage(QWidget):
    """乐谱生成页面 / Notation generation page."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._worker: QThread | None = None
        self._running = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("🎼 乐谱生成")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("将 MIDI 转录结果转换为可打印的乐谱 (五线谱/简谱/六线谱/总谱)")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # === 设置区域 ===
        settings = QGroupBox("⚙️  乐谱设置")
        form = QFormLayout(settings)
        form.setSpacing(12)

        # 谱式
        self.cb_format = QComboBox()
        for key, zh in NOTATION_ZH.items():
            self.cb_format.addItem(zh, key)
        form.addRow("谱式:", self.cb_format)

        # 标题
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("乐曲标题 (留空使用项目名)")
        form.addRow("标题:", self.input_title)

        # 作曲者
        self.input_composer = QLineEdit()
        self.input_composer.setPlaceholderText("作曲者 (可选)")
        form.addRow("作曲者:", self.input_composer)

        layout.addWidget(settings)

        # 运行按钮
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶️  生成乐谱")
        self.btn_run.setProperty("primary", True)
        self.btn_run.setFixedWidth(160)
        self.btn_run.clicked.connect(self._run_notation)
        btn_row.addWidget(self.btn_run)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # === 结果表格 ===
        results_group = QGroupBox("📄 生成结果")
        results_layout = QVBoxLayout(results_group)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "格式", "标题", "PDF", "MusicXML", "LilyPond"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        results_layout.addWidget(self.table)

        layout.addWidget(results_group)

        layout.addStretch()

    # ===== 执行乐谱生成 =====

    def _run_notation(self) -> None:
        """生成乐谱."""
        project = self.main_window.project
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页创建或加载项目。")
            return

        if self._running:
            return

        # 检查是否有可用的 MIDI
        has_midi = False
        for sname in ["piano", "guitar", "bass", "vocals"]:
            stem = project.stems.get(sname)
            if stem and stem.midi_path and stem.midi_path.exists():
                has_midi = True
                break

        if not has_midi:
            QMessageBox.warning(self, "提示", "没有可用的 MIDI 文件。请先运行 MIDI 转录。")
            return

        from src.gui.workers.notation_worker import NotationWorker

        fmt = self.cb_format.currentData()
        title = self.input_title.text().strip() or project.name
        composer = self.input_composer.text().strip()

        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_run.setText("⏳ 生成中...")
        self.main_window.set_status(f"正在生成 {NOTATION_ZH.get(fmt, fmt)}...", 0)

        self._worker = NotationWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=None,  # 使用所有有 MIDI 的 stem
            notation_format=fmt,
            title=title,
            composer=composer,
        )

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_progress(self, pct: int, msg: str) -> None:
        self.main_window.set_status(msg, pct)

    def _on_finished(self, result_dict: dict) -> None:
        """乐谱生成完成."""
        from src.core.notation.notation_formats import NotationFormat, NotationResult

        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重新生成")

        results = result_dict.get("results", {})

        self.table.setRowCount(0)
        for fmt, nresult in results.items():
            if not isinstance(nresult, object):
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            fmt_name = str(fmt).split(".")[-1] if hasattr(fmt, "name") else str(fmt)

            # 格式
            if hasattr(fmt, "display_name"):
                self.table.setItem(row, 0, QTableWidgetItem(fmt.display_name))
            else:
                self.table.setItem(row, 0, QTableWidgetItem(fmt_name))

            # 标题
            self.table.setItem(row, 1, QTableWidgetItem(
                self.input_title.text().strip() or (self.main_window.project.name if self.main_window.project else "-")
            ))

            # PDF
            pdf = str(nresult.pdf_path) if getattr(nresult, "pdf_path", None) else "-"
            pdf_item = QTableWidgetItem("📄 PDF" if pdf != "-" else "-")
            pdf_item.setToolTip(pdf)
            self.table.setItem(row, 2, pdf_item)

            # MusicXML
            mxml = str(nresult.musicxml_path) if getattr(nresult, "musicxml_path", None) else "-"
            mxml_item = QTableWidgetItem("🎵 XML" if mxml != "-" else "-")
            mxml_item.setToolTip(mxml)
            self.table.setItem(row, 3, mxml_item)

            # LilyPond
            ly = str(nresult.ly_path) if getattr(nresult, "ly_path", None) else "-"
            ly_item = QTableWidgetItem("📝 .ly" if ly != "-" else "-")
            ly_item.setToolTip(ly)
            self.table.setItem(row, 4, ly_item)

        self.main_window.set_status("乐谱生成完成!", 100)
        self._thread.quit()
        self._thread.wait()

    def _on_error(self, msg: str) -> None:
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重试")
        self.main_window.set_status(f"乐谱生成失败: {msg}")
        QMessageBox.critical(self, "生成失败", msg)
        self._thread.quit()
        self._thread.wait()

    # ===== 生命周期 =====

    def on_enter(self) -> None:
        """进入页面时刷新."""
        project = self.main_window.project
        if project:
            self.input_title.setPlaceholderText(f"乐曲标题 (留空使用: {project.name})")

    def on_leave(self) -> None:
        pass

