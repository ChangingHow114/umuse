"""音符页面 / Transcription & Notation Page.

MIDI 转录 + 乐谱生成整合页面。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDoubleSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QScrollArea, QLineEdit, QApplication,
)
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices

if TYPE_CHECKING:
    from src.gui.windows.main_window import MainWindow

MELODIC_STEMS = ["piano", "guitar", "bass", "vocals"]
MELODIC_STEMS_ZH = {
    "piano": "钢琴", "guitar": "吉他", "bass": "贝斯", "vocals": "人声",
}

NOTATION_FORMATS = ["staff", "jianpu", "tablature", "full_score", "all"]
NOTATION_ZH = {
    "staff": "五线谱",
    "jianpu": "简谱",
    "tablature": "六线谱 (吉他/贝斯)",
    "full_score": "总谱 (全部乐器)",
    "all": "全部格式",
}


class TranscriptionPage(QWidget):
    """音符页面 / Transcription + Notation page."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._trans_worker: QThread | None = None
        self._notation_worker: QThread | None = None
        self._trans_running = False
        self._notation_running = False

        # 缓存 MIDI 路径 (用于打开/复制)
        self._midi_paths: dict[str, Path | None] = {}
        # 缓存乐谱路径
        self._notation_paths: list[dict] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        # 外层用 ScrollArea 包裹
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ==========================================
        # 第一部分: MIDI 转录
        # ==========================================
        title = QLabel("🎹 MIDI 转录")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("使用 basic-pitch ONNX 将旋律乐器音频转录为 MIDI")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # --- 转录设置 ---
        trans_settings = QGroupBox("⚙️  转录设置")
        form = QFormLayout(trans_settings)
        form.setSpacing(12)

        self.cb_stem = QComboBox()
        form.addRow("目标 Stem:", self.cb_stem)

        self.onset_threshold = QDoubleSpinBox()
        self.onset_threshold.setRange(0.1, 0.99)
        self.onset_threshold.setValue(0.5)
        self.onset_threshold.setSingleStep(0.05)
        self.onset_threshold.setToolTip("越低检测越多音符 (可能产生噪音)")
        form.addRow("起音阈值:", self.onset_threshold)

        self.frame_threshold = QDoubleSpinBox()
        self.frame_threshold.setRange(0.1, 0.99)
        self.frame_threshold.setValue(0.3)
        self.frame_threshold.setSingleStep(0.05)
        form.addRow("帧阈值:", self.frame_threshold)

        self.min_note_len = QDoubleSpinBox()
        self.min_note_len.setRange(10, 500)
        self.min_note_len.setValue(58.0)
        self.min_note_len.setSuffix(" ms")
        form.addRow("最短音符:", self.min_note_len)

        self.cb_clean = QCheckBox("转录后自动清洗 MIDI (合并重叠音, 归一化力度)")
        self.cb_clean.setChecked(True)
        form.addRow("", self.cb_clean)

        layout.addWidget(trans_settings)

        # 转录运行按钮
        btn_row1 = QHBoxLayout()
        self.btn_run_trans = QPushButton("▶️  开始转录")
        self.btn_run_trans.setProperty("primary", True)
        self.btn_run_trans.setFixedWidth(160)
        self.btn_run_trans.clicked.connect(self._run_transcription)
        btn_row1.addWidget(self.btn_run_trans)
        btn_row1.addStretch()
        layout.addLayout(btn_row1)

        # --- MIDI 结果表格 ---
        midi_group = QGroupBox("📊 MIDI 转录结果")
        midi_layout = QVBoxLayout(midi_group)

        self.midi_table = QTableWidget(0, 5)
        self.midi_table.setHorizontalHeaderLabels([
            "Stem", "音符数", "MIDI 文件", "", ""
        ])
        self.midi_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.midi_table.verticalHeader().setVisible(False)
        self.midi_table.setAlternatingRowColors(False)
        midi_layout.addWidget(self.midi_table)

        layout.addWidget(midi_group)

        # ==========================================
        # 分隔线
        # ==========================================
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2D2045; margin: 8px 0;")
        layout.addWidget(sep)

        # ==========================================
        # 第二部分: 乐谱生成
        # ==========================================
        notation_title = QLabel("🎼 乐谱生成")
        notation_title.setObjectName("page_title")
        layout.addWidget(notation_title)

        notation_sub = QLabel("将转录好的 MIDI 转换为可打印的乐谱 (需安装 LilyPond)")
        notation_sub.setObjectName("page_subtitle")
        layout.addWidget(notation_sub)

        # --- 乐谱设置 ---
        notation_settings = QGroupBox("⚙️  乐谱设置")
        nform = QFormLayout(notation_settings)
        nform.setSpacing(12)

        self.cb_notation_fmt = QComboBox()
        for key, zh in NOTATION_ZH.items():
            self.cb_notation_fmt.addItem(zh, key)
        nform.addRow("谱式:", self.cb_notation_fmt)

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("乐曲标题 (留空使用项目名)")
        nform.addRow("标题:", self.input_title)

        self.input_composer = QLineEdit()
        self.input_composer.setPlaceholderText("作曲者 (可选)")
        nform.addRow("作曲者:", self.input_composer)

        layout.addWidget(notation_settings)

        # 乐谱运行按钮
        btn_row2 = QHBoxLayout()
        self.btn_run_notation = QPushButton("▶️  生成乐谱")
        self.btn_run_notation.setProperty("primary", True)
        self.btn_run_notation.setFixedWidth(160)
        self.btn_run_notation.clicked.connect(self._run_notation)
        btn_row2.addWidget(self.btn_run_notation)
        btn_row2.addStretch()
        layout.addLayout(btn_row2)

        # --- 乐谱结果表格 ---
        notation_group = QGroupBox("📄 乐谱结果")
        nresult_layout = QVBoxLayout(notation_group)

        self.notation_table = QTableWidget(0, 6)
        self.notation_table.setHorizontalHeaderLabels([
            "格式", "标题", "PDF", "MusicXML", "LilyPond", ""
        ])
        self.notation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.notation_table.verticalHeader().setVisible(False)
        nresult_layout.addWidget(self.notation_table)

        layout.addWidget(notation_group)

        layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    # ===== MIDI 转录 =====

    def _run_transcription(self) -> None:
        """执行 MIDI 转录."""
        project = self.main_window.project
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页创建或加载项目。")
            return

        if self._trans_running:
            return

        stem_name = self.cb_stem.currentData()
        if not project.stems.get(stem_name) or not project.stems[stem_name].path:
            QMessageBox.warning(self, "提示", f"Stem \"{stem_name}\" 尚未分离，请先运行分轨。")
            return

        from src.gui.workers.transcription_worker import TranscriptionWorker

        self._trans_running = True
        self.btn_run_trans.setEnabled(False)
        self.btn_run_trans.setText("⏳ 转录中...")
        self.main_window.set_status(f"正在转录 {MELODIC_STEMS_ZH.get(stem_name, stem_name)}...", 0)

        self._trans_worker = TranscriptionWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=stem_name,
            onset_threshold=self.onset_threshold.value(),
            frame_threshold=self.frame_threshold.value(),
            minimum_note_length=self.min_note_len.value(),
            clean_midi_output=self.cb_clean.isChecked(),
        )

        self._trans_thread = QThread()
        self._trans_worker.moveToThread(self._trans_thread)

        self._trans_thread.started.connect(self._trans_worker.run)
        self._trans_worker.progress.connect(self._on_trans_progress)
        self._trans_worker.finished.connect(self._on_trans_finished)
        self._trans_worker.error.connect(self._on_trans_error)
        self._trans_thread.finished.connect(self._trans_thread.deleteLater)

        self._trans_thread.start()

    def _on_trans_progress(self, pct: int, msg: str) -> None:
        self.main_window.set_status(msg, pct)

    def _on_trans_finished(self, results: dict[str, dict]) -> None:
        """转录完成."""
        self._trans_running = False
        self.btn_run_trans.setEnabled(True)
        self.btn_run_trans.setText("▶️  重新转录")

        # 更新表格
        self.midi_table.setRowCount(0)
        for sname, data in results.items():
            row = self.midi_table.rowCount()
            self.midi_table.insertRow(row)

            midi_path = data.get("midi_path")
            note_count = str(data.get("note_count", 0))

            clean_info = "-"
            if data.get("clean_report"):
                clean_info = data["clean_report"].summary()

            self.midi_table.setItem(row, 0, QTableWidgetItem(MELODIC_STEMS_ZH.get(sname, sname)))
            self.midi_table.setItem(row, 1, QTableWidgetItem(note_count))

            # MIDI 文件名
            if midi_path:
                path = Path(midi_path)
                self._midi_paths[sname] = path
                self.midi_table.setItem(row, 2, QTableWidgetItem(path.name))
            else:
                self._midi_paths[sname] = None
                self.midi_table.setItem(row, 2, QTableWidgetItem("-"))

            self.midi_table.setItem(row, 3, QTableWidgetItem(clean_info))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            btn_open = QPushButton("📂 打开")
            btn_open.setFixedSize(60, 22)
            btn_open.setStyleSheet(self._mini_btn_style())
            btn_open.clicked.connect(lambda checked=False, sn=sname: self._open_midi(sn))
            btn_open.setEnabled(bool(midi_path))

            btn_copy = QPushButton("📋 复制")
            btn_copy.setFixedSize(60, 22)
            btn_copy.setStyleSheet(self._mini_btn_style())
            btn_copy.clicked.connect(lambda checked=False, sn=sname: self._copy_midi(sn))
            btn_copy.setEnabled(bool(midi_path))

            btn_layout.addWidget(btn_open)
            btn_layout.addWidget(btn_copy)
            self.midi_table.setCellWidget(row, 4, btn_widget)

        self.main_window.set_status("转录完成!", 100)
        self._trans_thread.quit()
        self._trans_thread.wait()

    def _on_trans_error(self, msg: str) -> None:
        self._trans_running = False
        self.btn_run_trans.setEnabled(True)
        self.btn_run_trans.setText("▶️  重试")
        self.main_window.set_status(f"转录失败: {msg}")
        QMessageBox.critical(self, "转录失败", msg)
        self._trans_thread.quit()
        self._trans_thread.wait()

    def _open_midi(self, sname: str) -> None:
        """在 Finder 中打开 MIDI 文件所在目录."""
        path = self._midi_paths.get(sname)
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        else:
            QMessageBox.information(self, "提示", f"「{MELODIC_STEMS_ZH.get(sname, sname)}」的 MIDI 文件不存在。")

    def _copy_midi(self, sname: str) -> None:
        """复制 MIDI 文件路径."""
        path = self._midi_paths.get(sname)
        if path and path.exists():
            QApplication.clipboard().setText(str(path))
            self.main_window.set_status(f"已复制: {path.name}")
        else:
            QMessageBox.information(self, "提示", f"「{MELODIC_STEMS_ZH.get(sname, sname)}」的 MIDI 文件不存在。")

    # ===== 乐谱生成 =====

    def _run_notation(self) -> None:
        """生成乐谱."""
        project = self.main_window.project
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页创建或加载项目。")
            return

        if self._notation_running:
            return

        # 检查是否有可用的 MIDI
        has_midi = False
        for sname in MELODIC_STEMS:
            stem = project.stems.get(sname)
            if stem and stem.midi_path and stem.midi_path.exists():
                has_midi = True
                break

        if not has_midi:
            QMessageBox.warning(self, "提示", "没有可用的 MIDI 文件。请先运行 MIDI 转录。")
            return

        from src.gui.workers.notation_worker import NotationWorker

        fmt = self.cb_notation_fmt.currentData()
        title = self.input_title.text().strip() or project.name
        composer = self.input_composer.text().strip()

        self._notation_running = True
        self.btn_run_notation.setEnabled(False)
        self.btn_run_notation.setText("⏳ 生成中...")
        self.main_window.set_status(f"正在生成 {NOTATION_ZH.get(fmt, fmt)}...", 0)

        self._notation_worker = NotationWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=None,
            notation_format=fmt,
            title=title,
            composer=composer,
        )

        self._notation_thread = QThread()
        self._notation_worker.moveToThread(self._notation_thread)

        self._notation_thread.started.connect(self._notation_worker.run)
        self._notation_worker.progress.connect(self._on_notation_progress)
        self._notation_worker.finished.connect(self._on_notation_finished)
        self._notation_worker.error.connect(self._on_notation_error)
        self._notation_thread.finished.connect(self._notation_thread.deleteLater)

        self._notation_thread.start()

    def _on_notation_progress(self, pct: int, msg: str) -> None:
        self.main_window.set_status(msg, pct)

    def _on_notation_finished(self, result_dict: dict) -> None:
        """乐谱生成完成."""
        self._notation_running = False
        self.btn_run_notation.setEnabled(True)
        self.btn_run_notation.setText("▶️  重新生成")

        results = result_dict.get("results", {})
        self._notation_paths.clear()

        self.notation_table.setRowCount(0)
        for fmt, nresult in results.items():
            if not isinstance(nresult, object):
                continue

            row = self.notation_table.rowCount()
            self.notation_table.insertRow(row)

            fmt_name = str(fmt).split(".")[-1] if hasattr(fmt, "name") else str(fmt)

            # 格式
            if hasattr(fmt, "display_name"):
                self.notation_table.setItem(row, 0, QTableWidgetItem(fmt.display_name))
            else:
                self.notation_table.setItem(row, 0, QTableWidgetItem(fmt_name))

            # 标题
            self.notation_table.setItem(row, 1, QTableWidgetItem(
                self.input_title.text().strip() or (
                    self.main_window.project.name if self.main_window.project else "-"
                )
            ))

            # PDF
            pdf = str(nresult.pdf_path) if getattr(nresult, "pdf_path", None) else None
            pdf_item = QTableWidgetItem("📄 PDF" if pdf else "-")
            pdf_item.setToolTip(pdf or "")
            self.notation_table.setItem(row, 2, pdf_item)

            # MusicXML
            mxml = str(nresult.musicxml_path) if getattr(nresult, "musicxml_path", None) else None
            mxml_item = QTableWidgetItem("🎵 XML" if mxml else "-")
            mxml_item.setToolTip(mxml or "")
            self.notation_table.setItem(row, 3, mxml_item)

            # LilyPond
            ly = str(nresult.ly_path) if getattr(nresult, "ly_path", None) else None
            ly_item = QTableWidgetItem("📝 .ly" if ly else "-")
            ly_item.setToolTip(ly or "")
            self.notation_table.setItem(row, 4, ly_item)

            # 操作按钮
            paths_info = {
                "pdf": pdf,
                "mxml": mxml,
                "ly": ly,
                "fmt": fmt_name,
            }
            self._notation_paths.append(paths_info)

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            btn_open = QPushButton("📂 打开")
            btn_open.setFixedSize(60, 22)
            btn_open.setStyleSheet(self._mini_btn_style())
            btn_open.clicked.connect(
                lambda checked=False, r=row: self._open_notation_dir(r)
            )

            btn_copy = QPushButton("📋 复制")
            btn_copy.setFixedSize(60, 22)
            btn_copy.setStyleSheet(self._mini_btn_style())
            btn_copy.clicked.connect(
                lambda checked=False, r=row: self._copy_notation_path(r)
            )

            btn_layout.addWidget(btn_open)
            btn_layout.addWidget(btn_copy)
            self.notation_table.setCellWidget(row, 5, btn_widget)

        self.main_window.set_status("乐谱生成完成!", 100)
        self._notation_thread.quit()
        self._notation_thread.wait()

    def _on_notation_error(self, msg: str) -> None:
        self._notation_running = False
        self.btn_run_notation.setEnabled(True)
        self.btn_run_notation.setText("▶️  重试")
        self.main_window.set_status(f"乐谱生成失败: {msg}")
        QMessageBox.critical(self, "生成失败", msg)
        self._notation_thread.quit()
        self._notation_thread.wait()

    def _open_notation_dir(self, row: int) -> None:
        """打开乐谱所在目录."""
        if row < len(self._notation_paths):
            info = self._notation_paths[row]
            # 优先打开 PDF 所在目录
            for key in ("pdf", "mxml", "ly"):
                p = info.get(key)
                if p and Path(p).exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent)))
                    return
        QMessageBox.information(self, "提示", "乐谱文件不存在。")

    def _copy_notation_path(self, row: int) -> None:
        """复制乐谱文件路径 (优先 PDF)."""
        if row < len(self._notation_paths):
            info = self._notation_paths[row]
            for key in ("pdf", "mxml", "ly"):
                p = info.get(key)
                if p and Path(p).exists():
                    QApplication.clipboard().setText(str(p))
                    self.main_window.set_status(f"已复制: {Path(p).name}")
                    return
        QMessageBox.information(self, "提示", "乐谱文件不存在。")

    # ===== 工具方法 =====

    @staticmethod
    def _mini_btn_style() -> str:
        """迷你按钮样式."""
        return """
            QPushButton {
                background-color: #2D2045; color: #C8B8E0;
                border: 1px solid #3D3055; border-radius: 4px;
                font-size: 11px; padding: 2px 6px;
            }
            QPushButton:hover { background-color: #3D3055; color: #E8E0F0; }
            QPushButton:disabled { background-color: #1A1128; color: #5A5070; }
        """

    # ===== 生命周期 =====

    def on_enter(self) -> None:
        """进入页面时刷新."""
        project = self.main_window.project
        self.cb_stem.clear()
        self._midi_paths.clear()

        if not project:
            return

        for sname in MELODIC_STEMS:
            stem = project.stems.get(sname)
            if stem:
                has_data = stem.path and stem.path.exists() if stem.path else False
                has_midi = stem.midi_path and stem.midi_path.exists() if stem else False
                status = "✅" if has_data and has_midi else "✅" if has_data else "⏳"
                label = f"{status} {MELODIC_STEMS_ZH[sname]} ({sname})"
                self.cb_stem.addItem(label, sname)
                if has_midi:
                    self._midi_paths[sname] = stem.midi_path

        self.input_title.setPlaceholderText(f"乐曲标题 (留空使用: {project.name})")

        # 恢复缓存的 MIDI 结果显示
        self._restore_midi_table()
        # 恢复缓存的乐谱路径
        self._restore_notation_paths()

    def _restore_midi_table(self) -> None:
        """从 project 恢复 MIDI 表格数据."""
        project = self.main_window.project
        if not project:
            return

        self.midi_table.setRowCount(0)
        for sname in MELODIC_STEMS:
            stem = project.stems.get(sname)
            if not stem or not stem.midi_path or not stem.midi_path.exists():
                continue

            row = self.midi_table.rowCount()
            self.midi_table.insertRow(row)

            path = stem.midi_path
            self._midi_paths[sname] = path

            self.midi_table.setItem(row, 0, QTableWidgetItem(MELODIC_STEMS_ZH.get(sname, sname)))
            self.midi_table.setItem(row, 1, QTableWidgetItem("-"))
            self.midi_table.setItem(row, 2, QTableWidgetItem(path.name))
            self.midi_table.setItem(row, 3, QTableWidgetItem("(缓存)"))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            btn_open = QPushButton("📂 打开")
            btn_open.setFixedSize(60, 22)
            btn_open.setStyleSheet(self._mini_btn_style())
            btn_open.clicked.connect(lambda checked=False, sn=sname: self._open_midi(sn))

            btn_copy = QPushButton("📋 复制")
            btn_copy.setFixedSize(60, 22)
            btn_copy.setStyleSheet(self._mini_btn_style())
            btn_copy.clicked.connect(lambda checked=False, sn=sname: self._copy_midi(sn))

            btn_layout.addWidget(btn_open)
            btn_layout.addWidget(btn_copy)
            self.midi_table.setCellWidget(row, 4, btn_widget)

    def _restore_notation_paths(self) -> None:
        """从 project 恢复乐谱路径缓存."""
        project = self.main_window.project
        if not project or not project.output_dir:
            return
        notation_dir = project.output_dir / "notation"
        if notation_dir.exists():
            # 扫描已知文件
            self._notation_paths.clear()
            for pdf in sorted(notation_dir.rglob("*.pdf")):
                self._notation_paths.append({
                    "pdf": str(pdf),
                    "mxml": None,
                    "ly": None,
                    "fmt": "staff",
                })

    def on_leave(self) -> None:
        pass
