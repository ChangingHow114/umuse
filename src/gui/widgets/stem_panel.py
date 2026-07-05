"""Stem 信息卡片 / Stem Info Card.

展示单个 Stem 的名称、文件大小、路径和波形占位图。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Qt

from src.gui.widgets.waveform_placeholder import WaveformPlaceholder


class StemPanel(QFrame):
    """Stem 信息卡片 / Stem information card.

    显示乐器名、文件大小、路径、波形占位色块。

    用法:
        panel = StemPanel("piano", "钢琴")
        panel.set_stem_path(Path("output/piano.wav"))
    """

    COLORS = {
        "piano": "#7C3AED",
        "guitar": "#00F5FF",
        "bass": "#F59E0B",
        "drums": "#EF4444",
        "vocals": "#10B981",
        "other": "#5A5070",
    }

    def __init__(
        self,
        stem_name: str,
        name_zh: str,
        parent: QFrame | None = None,
    ) -> None:
        super().__init__(parent)
        self._stem_name = stem_name
        self._name_zh = name_zh
        self._color = self.COLORS.get(stem_name, "#5A5070")

        self.setObjectName("stem_panel")
        self.setStyleSheet(f"""
            QFrame#stem_panel {{
                background-color: #1A1128;
                border: 1px solid #2D2045;
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame#stem_panel:hover {{
                border-color: {self._color};
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 标题行
        header = QHBoxLayout()

        # 彩色小方块指示器
        ind = QLabel("  ")
        ind.setFixedSize(12, 12)
        ind.setStyleSheet(f"""
            background-color: {self._color};
            border-radius: 2px;
        """)
        header.addWidget(ind)

        self.title_label = QLabel(self._name_zh)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self.title_label, 1)

        self.status_label = QLabel("⏳")
        self.status_label.setStyleSheet("font-size: 12px; color: #5A5070;")
        header.addWidget(self.status_label)

        layout.addLayout(header)

        # 波形占位 / Waveform placeholder
        self.waveform = WaveformPlaceholder(self._color)
        layout.addWidget(self.waveform)

        # 信息行
        info_row = QHBoxLayout()
        self.size_label = QLabel("")
        self.size_label.setObjectName("info_label")
        info_row.addWidget(self.size_label)
        info_row.addStretch()
        layout.addLayout(info_row)

    def set_stem_path(self, path: Path | None) -> None:
        """设置 Stem 文件路径并更新显示.

        Args:
            path: Stem 音频文件路径 (None = 无数据)
        """
        if path and path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            self.status_label.setText("✅")
            self.status_label.setStyleSheet("font-size: 12px; color: #10B981;")
            self.size_label.setText(f"{path.name} ({size_mb:.1f} MB)")
            self.setToolTip(str(path))
        else:
            self.status_label.setText("⏳")
            self.status_label.setStyleSheet("font-size: 12px; color: #5A5070;")
            self.size_label.setText("等待分离...")

    def clear(self) -> None:
        """清空显示."""
        self.status_label.setText("⏳")
        self.status_label.setStyleSheet("font-size: 12px; color: #5A5070;")
        self.size_label.setText("")

