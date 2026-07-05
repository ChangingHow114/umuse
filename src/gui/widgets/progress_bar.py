"""青色渐变进度条 / Cyan Gradient Progress Bar.

自定义 QProgressBar，深紫底 + 青色渐变填充块。
"""

from __future__ import annotations

from PySide6.QtWidgets import QProgressBar, QWidget
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen, QFont
from PySide6.QtCore import Qt, QRectF


class GradientProgressBar(QProgressBar):
    """青色渐变进度条 / Gradient progress bar with cyan accent.

    用法:
        bar = GradientProgressBar()
        bar.setRange(0, 100)
        bar.setValue(42)
    """

    COLOR_BG = QColor("#231840")       # bg_surface
    COLOR_BORDER = QColor("#2D2045")   # border
    COLOR_TEXT = QColor("#E8E0F0")     # text_primary
    COLOR_GRADIENT_START = QColor("#00F5FF")   # accent
    COLOR_GRADIENT_END = QColor("#7C3AED")     # primary

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextVisible(True)
        self.setMinimumHeight(18)
        self.setMaximumHeight(18)
        self._font = QFont("PingFang SC", 9)

    def paintEvent(self, event) -> None:
        """自定义绘制 / Custom paint."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        bar_rect = QRectF(
            rect.x() + 1, rect.y() + 1,
            rect.width() - 2, rect.height() - 2,
        )

        # 背景
        painter.setPen(QPen(self.COLOR_BORDER, 1))
        painter.setBrush(QBrush(self.COLOR_BG))
        painter.drawRoundedRect(bar_rect, 4, 4)

        # 进度填充
        if self.value() > 0:
            pct = min(self.value(), self.maximum()) / max(self.maximum(), 1)
            fill_width = bar_rect.width() * pct
            if fill_width > 2:
                fill_rect = QRectF(
                    bar_rect.x(), bar_rect.y(),
                    fill_width, bar_rect.height(),
                )

                gradient = QLinearGradient(0, 0, fill_rect.width(), 0)
                gradient.setColorAt(0.0, self.COLOR_GRADIENT_START)
                gradient.setColorAt(1.0, self.COLOR_GRADIENT_END)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(fill_rect, 4, 4)

        # 文字
        if self.isTextVisible():
            painter.setFont(self._font)
            painter.setPen(self.COLOR_TEXT)
            painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, self.text())

        painter.end()

