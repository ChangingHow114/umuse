"""主窗口 / Main Window.

侧边栏导航 + QStackedWidget 内容区 + 状态栏。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton, QStatusBar,
    QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from src.config.settings import Settings
from src.core.project import Project
from src.core.pipeline import PipelineManager

if TYPE_CHECKING:
    from src.gui.pages.project_page import ProjectPage
    from src.gui.pages.separation_page import SeparationPage
    from src.gui.pages.transcription_page import TranscriptionPage
    from src.gui.pages.timbre_page import TimbrePage
    from src.gui.pages.effects_page import EffectsPage


# 导航按钮配置 / Navigation button config
# 注: 乐谱生成已合并到「转录」页面内, 不再独立显示
NAV_BUTTONS = [
    ("project", "📁  项目"),
    ("separation", "🎛️  分轨"),
    ("transcription", "🎹  音符"),
    ("timbre", "🎸  音色"),
    ("effects", "🎚️  效果"),
]

PAGE_INDEX = {
    "project": 0,
    "separation": 1,
    "transcription": 2,
    "timbre": 3,
    "effects": 4,
}


class MainWindow(QMainWindow):
    """UMuse 主窗口 / Main application window.

    持有共享状态: project, settings, pipeline_manager。
    通过侧边栏切换 6 个功能页面。
    """

    def __init__(self) -> None:
        super().__init__()

        # ===== 共享状态 / Shared State =====
        self.settings = Settings().load()
        self.project: Project | None = None
        self.pipeline_manager: PipelineManager | None = None

        # ===== 窗口基本属性 / Window Properties =====
        self.setWindowTitle("UMuse — AI 音乐逆向工程工作站")
        self.resize(
            self.settings.ui.window_width,
            self.settings.ui.window_height,
        )
        self.setMinimumSize(900, 600)

        # ===== 中心区域 =====
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ===== 侧边栏 =====
        self.sidebar = self._create_sidebar()
        root_layout.addWidget(self.sidebar)

        # ===== 内容区 =====
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)

        root_layout.addLayout(content_layout, 1)

        # ===== 创建页面 (惰性导入) =====
        self._create_pages()

        # ===== 状态栏 =====
        self._create_status_bar()

        # 默认选中第一页
        self._nav_buttons["project"].setProperty("selected", True)
        self._nav_buttons["project"].style().unpolish(self._nav_buttons["project"])
        self._nav_buttons["project"].style().polish(self._nav_buttons["project"])
        self.stack.setCurrentIndex(0)

    # ===== 侧边栏 / Sidebar =====

    def _create_sidebar(self) -> QWidget:
        """创建侧边栏 / Create sidebar widget."""
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(self.settings.ui.sidebar_width)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("🎵 UMuse")
        logo.setObjectName("logo")
        layout.addWidget(logo)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2D2045; margin: 0 12px;")
        layout.addWidget(sep)

        layout.addSpacing(8)

        # 导航按钮
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label in NAV_BUTTONS:
            btn = QPushButton(label)
            btn.setProperty("nav", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch()

        # 设置按钮
        btn_settings = QPushButton("⚙️  设置")
        btn_settings.setObjectName("btn_settings")
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(btn_settings)

        # 版本号
        version_label = QLabel("v0.1.0 — Phase 6")
        version_label.setObjectName("version")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        return sidebar

    def _switch_page(self, key: str) -> None:
        """切换页面 / Switch to page by key.

        Args:
            key: 页面标识 (project/separation/transcription/timbre/effects/notation)
        """
        # 更新导航按钮状态
        for k, btn in self._nav_buttons.items():
            btn.setProperty("selected", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # 离开旧页面
        old_idx = self.stack.currentIndex()
        old_page = self.stack.widget(old_idx)
        if old_page and hasattr(old_page, "on_leave"):
            old_page.on_leave()

        # 切换
        self.stack.setCurrentIndex(PAGE_INDEX[key])

        # 进入新页面
        new_page = self.stack.currentWidget()
        if new_page and hasattr(new_page, "on_enter"):
            new_page.on_enter()

        # 更新状态栏
        page_names = {
            "project": "项目", "separation": "分轨",
            "transcription": "音符", "timbre": "音色",
            "effects": "效果",
        }
        self.status_label.setText(f"📄 {page_names.get(key, key)}")

    # ===== 页面创建 =====

    def _create_pages(self) -> None:
        """创建所有页面 / Create all pages via lazy import."""
        from src.gui.pages.project_page import ProjectPage
        from src.gui.pages.separation_page import SeparationPage
        from src.gui.pages.transcription_page import TranscriptionPage
        from src.gui.pages.timbre_page import TimbrePage
        from src.gui.pages.effects_page import EffectsPage

        # Project (index 0)
        self.project_page: ProjectPage = ProjectPage(self)
        self.stack.addWidget(self.project_page)

        # Separation (index 1)
        self.separation_page: SeparationPage = SeparationPage(self)
        self.stack.addWidget(self.separation_page)

        # Transcription + Notation (index 2) — 乐谱生成整合在转录页面内
        self.transcription_page: TranscriptionPage = TranscriptionPage(self)
        self.stack.addWidget(self.transcription_page)

        # Timbre (index 3)
        self.timbre_page: TimbrePage = TimbrePage(self)
        self.stack.addWidget(self.timbre_page)

        # Effects (index 4)
        self.effects_page: EffectsPage = EffectsPage(self)
        self.stack.addWidget(self.effects_page)

    # ===== 状态栏 =====

    def _create_status_bar(self) -> None:
        """创建状态栏 / Create status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 项目名
        self.status_project = QLabel("📁 无项目")
        self.status_bar.addWidget(self.status_project)

        self.status_bar.addPermanentWidget(QWidget())  # spacer

        # 进度条
        self.status_progress = QProgressBar()
        self.status_progress.setFixedSize(QSize(150, 14))
        self.status_progress.setRange(0, 100)
        self.status_progress.setValue(0)
        self.status_progress.setVisible(False)
        self.status_bar.addPermanentWidget(self.status_progress)

        # 状态消息
        self.status_label = QLabel("就绪")
        self.status_bar.addPermanentWidget(self.status_label)

    # ===== 公共方法 / Public API =====

    def set_status(self, message: str, progress: int = -1) -> None:
        """更新状态栏 / Update status bar.

        Args:
            message: 状态消息
            progress: 进度值 (-1 = 隐藏进度条)
        """
        self.status_label.setText(message)
        if progress >= 0:
            self.status_progress.setVisible(True)
            self.status_progress.setValue(progress)
        else:
            self.status_progress.setVisible(False)

    def set_project(self, project: Project) -> None:
        """设置当前项目 / Set current project.

        Args:
            project: 项目实例
        """
        self.project = project
        self.pipeline_manager = PipelineManager(project, self.settings)
        self.status_project.setText(f"📁 {project.name}")

    def refresh_all_pages(self) -> None:
        """刷新所有页面 / Refresh all visible pages."""
        current = self.stack.currentWidget()
        if current and hasattr(current, "on_enter"):
            current.on_enter()

