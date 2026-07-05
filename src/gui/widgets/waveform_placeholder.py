"""波形占位色块 / Waveform Placeholder.

简单的彩色渐变矩形，用作 StemPanel 中的波形预览占位。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen
from PySide6.QtCore import Qt, QRectF


class WaveformPlaceholder(QWidget):
    """波形占位色块 / Simple gradient rectangle for waveform preview.

    用法:
        wp = WaveformPlaceholder("#7C3AED")
    """

    def __init__(self, color: str = "#7C3AED", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._color_dark = QColor(color).darker(200)
        self.setMinimumHeight(40)
        self.setMaximumHeight(60)

    def set_color(self, color: str) -> None:
        """更新颜色 / Update color.

        Args:
            color: CSS 颜色字符串
        """
        self._color = QColor(color)
        self._color_dark = QColor(color).darker(200)
        self.update()  # 触发重绘

    def paintEvent(self, event) -> None:
        """自定义绘制渐变背景 + 模拟波形线."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        r = QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2)

        # 背景渐变 (深色→更暗)
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0.0, self._color.darker(180))
        gradient.setColorAt(0.5, self._color.darker(220))
        gradient.setColorAt(1.0, self._color.darker(260))

        painter.setPen(QPen(self._color.darker(150), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(r, 4, 4)

        # 模拟波形中线 (亮色水平线)
        mid_y = rect.height() / 2
        painter.setPen(QPen(self._color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(r.x()) + 4, int(mid_y), int(r.right()) - 4, int(mid_y))

        painter.end()

