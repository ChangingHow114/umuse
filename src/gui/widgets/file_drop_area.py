"""文件拖放区域 / File Drop Area.

支持拖放或点击浏览选择音频文件。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent


class FileDropArea(QFrame):
    """文件拖放区域 / Drag-and-drop file area.

    支持拖放音频文件或点击浏览。

    信号:
        file_selected(str): 用户选择了文件，传递文件路径

    用法:
        drop = FileDropArea()
        drop.file_selected.connect(on_file_picked)
        layout.addWidget(drop)
    """

    file_selected = Signal(str)

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("file_drop_area")
        self.setStyleSheet("""
            QFrame#file_drop_area {
                background-color: #231840;
                border: 2px dashed #5A5070;
                border-radius: 12px;
                min-height: 140px;
            }
            QFrame#file_drop_area:hover {
                border-color: #A78BFA;
                background-color: #2D1F50;
            }
            QFrame#file_drop_area[drag_over="true"] {
                border-color: #00F5FF;
                background-color: #1A3A4A;
            }
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        # 图标
        icon_label = QLabel("🎵")
        icon_label.setStyleSheet("font-size: 32px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 提示文字
        hint = QLabel("拖放音频文件到此处\n或点击下方按钮浏览")
        hint.setStyleSheet("color: #9B8FB0; font-size: 13px; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #A78BFA; font-size: 12px; background: transparent;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # 浏览按钮
        btn = QPushButton("浏览文件...")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #7C3AED;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #A78BFA;
            }
        """)
        btn.setFixedWidth(140)
        btn.clicked.connect(self._browse)

        btn_wrapper = QHBoxLayout()
        btn_wrapper.addStretch()
        btn_wrapper.addWidget(btn)
        btn_wrapper.addStretch()
        layout.addLayout(btn_wrapper)

    def _browse(self) -> None:
        """浏览选择文件."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择音频文件",
            "",
            "音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a *.aiff);;所有文件 (*.*)",
        )
        if file_path:
            self._status_label.setText(f"已选择: {file_path}")
            self.file_selected.emit(file_path)

    # ===== 拖放事件 / Drag & Drop =====

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """拖入时高亮."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_over", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        """拖出时恢复."""
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        """放下文件时处理."""
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)

        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            self._status_label.setText(f"已选择: {file_path}")
            self.file_selected.emit(file_path)

