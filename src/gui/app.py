"""UMuse GUI 应用入口 / GUI Application Entry.

QApplication 初始化、主题加载、主窗口启动。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt

from src.gui.theme import generate_stylesheet
from src.gui.windows.main_window import MainWindow


def main() -> int:
    """启动 GUI 应用 / Launch GUI application.

    Returns:
        退出码 (0 = 正常退出)
    """
    from src.config import setup_logging

    # 初始化日志 (GUI 模式: 全部日志写入文件, 控制台仅 ERROR)
    setup_logging(
        log_file=Path(__file__).parent.parent.parent / "logs" / "umuse_gui.log",
        console_level=logging.ERROR,
    )

    # 高 DPI 支持 / High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("UMuse")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("UMuse")

    # 设置默认字体 / Set default font
    font = QFont("PingFang SC", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # 应用深紫科技风主题 / Apply dark purple tech theme
    stylesheet = generate_stylesheet()
    app.setStyleSheet(stylesheet)

    # 创建并显示主窗口 / Create and show main window
    window = MainWindow()
    window.show()

    # 事件循环 / Event loop
    exit_code = app.exec()

    # 显式清理，避免 Qt 退出时的 QThread 析构 SIGABRT
    # Qt 的 Metal GPU 线程可能在 atexit 回调中崩溃
    window.close()
    window.deleteLater()
    app.quit()

    return exit_code


if __name__ == "__main__":
    exit_code = main()
    # 使用 os._exit 强制退出，跳过 PySide6 atexit 清理中的 QThread 析构崩溃
    # SIGABRT 产生的原因: 程序退出时 Metal GPU 线程仍在运行, QThread::~QThread 触发 fatal
    import os
    os._exit(exit_code)

