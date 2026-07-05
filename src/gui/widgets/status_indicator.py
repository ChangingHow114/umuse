"""状态指示圆点 / Status Indicator Dot.

彩色小圆点，用于表示项目或任务状态。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtCore import Qt, QRectF


STATUS_COLORS = {
    "idle": "#5A5070",       # 空闲 - 灰色
    "running": "#F59E0B",    # 运行中 - 黄色
    "success": "#10B981",    # 成功 - 绿色
    "error": "#EF4444",      # 错误 - 红色
    "warning": "#F59E0B",    # 警告 - 橙色
}


class StatusIndicator(QWidget):
    """状态指示圆点 / Colored status dot.

    用法:
        ind = StatusIndicator("idle")       # 灰色圆点
        ind.set_status("success")           # 切换为绿色
    """

    SIZE = 10

    def __init__(
        self,
        status: str = "idle",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(STATUS_COLORS.get(status, "#5A5070"))
        self.setFixedSize(self.SIZE + 4, self.SIZE + 4)

    def set_status(self, status: str) -> None:
        """更新状态颜色.

        Args:
            status: 状态标识 (idle/running/success/error/warning)
        """
        self._color = QColor(STATUS_COLORS.get(status, "#5A5070"))
        self.update()

    def set_color(self, color: str) -> None:
        """直接设置颜色.

        Args:
            color: CSS 颜色字符串
        """
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        """自定义绘制圆点."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = self.SIZE / 2

        # 外发光
        glow = QColor(self._color)
        glow.setAlpha(60)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(
            QRectF(center_x - radius - 2, center_y - radius - 2,
                   (radius + 2) * 2, (radius + 2) * 2)
        )

        # 实心圆
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(
            QRectF(center_x - radius, center_y - radius,
                   radius * 2, radius * 2)
        )

        painter.end()

