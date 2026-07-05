"""可折叠设置区域 / Collapsible Section.

点击标题栏展开/收起内容区域。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont


class CollapsibleSection(QWidget):
    """可折叠分组区域 / Expandable settings group.

    用法:
        section = CollapsibleSection("高级设置")
        section.add_widget(my_setting_widget)
        layout.addWidget(section)
    """

    def __init__(
        self,
        title: str,
        collapsed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._collapsed = collapsed
        self._title_text = title

        self.setStyleSheet("""
            QWidget#collapsible_section {
                background-color: #1A1128;
                border: 1px solid #2D2045;
                border-radius: 6px;
            }
        """)
        self.setObjectName("collapsible_section")

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # 标题栏
        header = QFrame()
        header.setStyleSheet("background: transparent;")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        # 折叠图标
        self._toggle_btn = QPushButton("▶" if self._collapsed else "▼")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #9B8FB0;
                font-size: 10px;
                padding: 0;
            }
            QPushButton:hover { color: #A78BFA; }
        """)
        self._toggle_btn.clicked.connect(self.toggle)
        header_layout.addWidget(self._toggle_btn)

        # 标题
        title_label = QLabel(self._title_text)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; background: transparent;")
        title_layout = QHBoxLayout()
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        header_layout.addLayout(title_layout)

        self._main_layout.addWidget(header)

        # 内容区域
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 4, 12, 12)
        self._content_layout.setSpacing(8)
        self._main_layout.addWidget(self._content)

        if self._collapsed:
            self._content.setVisible(False)

    def add_widget(self, widget: QWidget) -> None:
        """向内容区域添加控件.

        Args:
            widget: 要添加的 QWidget
        """
        self._content_layout.addWidget(widget)

    def add_layout(self, layout: QHBoxLayout | QVBoxLayout) -> None:
        """向内容区域添加布局.

        Args:
            layout: 子布局
        """
        self._content_layout.addLayout(layout)

    def toggle(self) -> None:
        """切换展开/折叠."""
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")

    def set_collapsed(self, collapsed: bool) -> None:
        """设置折叠状态.

        Args:
            collapsed: True = 折叠, False = 展开
        """
        if self._collapsed != collapsed:
            self.toggle()

