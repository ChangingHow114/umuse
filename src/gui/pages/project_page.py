"""项目页面 / Project Page.

创建、加载、保存项目，选择音频文件，显示项目状态概览。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QFileDialog,
    QMessageBox, QGroupBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal

from src.core.project import Project, ProjectStatus
from src.core.audio.loader import get_audio_info, validate_audio

if TYPE_CHECKING:
    from src.gui.windows.main_window import MainWindow

STATUS_ZH: dict[ProjectStatus, str] = {
    ProjectStatus.CREATED: "📝 已创建",
    ProjectStatus.IMPORTING: "⏳ 导入中...",
    ProjectStatus.READY: "✅ 就绪",
    ProjectStatus.SEPARATING: "🔄 分轨中...",
    ProjectStatus.SEPARATED: "✅ 已分轨",
    ProjectStatus.TRANSCRIBING: "🎹 转录中...",
    ProjectStatus.TRANSCRIBED: "✅ 已转录",
    ProjectStatus.MATCHING: "🎸 音色匹配中...",
    ProjectStatus.MATCHED: "✅ 已匹配",
    ProjectStatus.ESTIMATING: "🎚️ 效果分析中...",
    ProjectStatus.ESTIMATED: "✅ 已分析",
    ProjectStatus.NOTATING: "🎼 制谱中...",
    ProjectStatus.COMPLETED: "🌟 已完成",
    ProjectStatus.FAILED: "❌ 失败",
}


class ProjectPage(QWidget):
    """项目页面 / Project management page."""

    project_created = Signal(Project)  # 项目创建/加载信号

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI / Build UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("📁 项目")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("创建新项目或加载已有项目，选择要分析的音频文件")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # === 新建项目区域 ===
        new_group = QGroupBox("🆕 新建项目")
        new_layout = QFormLayout(new_group)
        new_layout.setSpacing(12)

        # 项目名称
        name_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入项目名称 (可选，默认使用音频文件名)")
        name_row.addWidget(self.name_input)
        new_layout.addRow("项目名称:", name_row)

        # 音频文件选择
        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("选择音频文件 (.wav, .mp3, .flac)")
        self.file_input.setReadOnly(True)
        file_row.addWidget(self.file_input, 1)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_file)
        file_row.addWidget(btn_browse)

        new_layout.addRow("音频文件:", file_row)

        layout.addWidget(new_group)

        # 创建按钮
        btn_create = QPushButton("🚀 创建项目")
        btn_create.setProperty("primary", True)
        btn_create.setFixedWidth(180)
        btn_create.clicked.connect(self._create_project)
        layout.addWidget(btn_create, alignment=Qt.AlignmentFlag.AlignLeft)

        # === 或加载已有项目 ===
        sep_row = QHBoxLayout()
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet("background-color: #2D2045;")
        sep_row.addWidget(sep_line, 1)
        sep_row.addWidget(QLabel("  或  "))
        sep_row.addWidget(sep_line2 := QFrame())
        sep_line2.setFrameShape(QFrame.Shape.HLine)
        sep_line2.setStyleSheet("background-color: #2D2045;")
        sep_row.addWidget(sep_line2, 1)
        layout.addLayout(sep_row)

        btn_load = QPushButton("📂 加载已有项目")
        btn_load.clicked.connect(self._load_project)
        btn_load.setFixedWidth(180)
        layout.addWidget(btn_load, alignment=Qt.AlignmentFlag.AlignLeft)

        # === 项目信息概览 ===
        self.info_group = QGroupBox("📋 项目信息")
        self.info_layout = QFormLayout(self.info_group)
        self.info_layout.setSpacing(8)
        self.info_group.setVisible(False)
        layout.addWidget(self.info_group)

        layout.addStretch()

    # ===== 文件浏览 / Browse =====

    def _browse_file(self) -> None:
        """浏览选择音频文件."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择音频文件",
            "",
            "音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a *.aiff);;所有文件 (*.*)",
        )
        if file_path:
            self.file_input.setText(file_path)

    # ===== 项目创建 / Create =====

    def _create_project(self) -> None:
        """创建新项目."""
        from pathlib import Path

        audio_path = self.file_input.text().strip()
        if not audio_path:
            QMessageBox.warning(self, "提示", "请先选择音频文件。")
            return

        # 验证音频
        result = validate_audio(audio_path)
        if not result["valid"]:
            QMessageBox.critical(self, "音频无效", f"无法加载音频:\n{result['reason']}")
            return

        # 获取项目名
        name = self.name_input.text().strip() or Path(audio_path).stem

        # 输出目录
        output_dir = Path("output") / name

        try:
            project = Project(
                name=name,
                input_file=Path(audio_path),
                output_dir=output_dir,
            )
            project.ensure_output_dir()
        except Exception as e:
            QMessageBox.critical(self, "创建失败", f"无法创建项目:\n{e}")
            return

        # 通知 MainWindow
        self.main_window.set_project(project)
        self.project_created.emit(project)

        # 显示信息
        self._show_project_info()
        QMessageBox.information(
            self, "项目已创建",
            f"项目 \"{name}\" 创建成功!\n输出目录: {output_dir}",
        )

    def _load_project(self) -> None:
        """加载已有项目."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "加载项目文件",
            "output",
            "UMuse 项目 (*.json);;所有文件 (*.*)",
        )
        if not file_path:
            return

        try:
            project = Project.load(file_path)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载项目:\n{e}")
            return

        self.main_window.set_project(project)
        self.project_created.emit(project)

        # 回填 UI
        self.file_input.setText(str(project.input_file or ""))
        self.name_input.setText(project.name)
        self._show_project_info()

        QMessageBox.information(self, "项目已加载", f"项目 \"{project.name}\" 加载成功!")

    # ===== 信息展示 / Info Display =====

    def _show_project_info(self) -> None:
        """显示项目信息概览."""
        project = self.main_window.project
        if not project:
            return

        # 清空旧信息
        while self.info_layout.count():
            self.info_layout.removeRow(0)

        self.info_layout.addRow("项目名:", QLabel(project.name))

        if project.input_file:
            self.info_layout.addRow("音频文件:", QLabel(str(project.input_file)))
            try:
                info = get_audio_info(str(project.input_file))
                info_text = f"{info['duration_sec']:.1f} 秒 | {info['sample_rate']} Hz | {info['channels']} 通道"
                self.info_layout.addRow("音频信息:", QLabel(info_text))
            except Exception:
                pass

        self.info_layout.addRow("输出目录:", QLabel(str(project.output_dir)))

        status_zh = STATUS_ZH.get(project.status, str(project.status))
        self.info_layout.addRow("状态:", QLabel(status_zh))

        # Stem 列表
        active_stems = [s for s in project.stems.values() if s.path]
        if active_stems:
            stem_text = ", ".join(f"{s.name_zh}" for s in active_stems)
            self.info_layout.addRow("已分离:", QLabel(stem_text))

        self.info_group.setVisible(True)

    # ===== 生命周期 / Lifecycle =====

    def on_enter(self) -> None:
        """进入页面时刷新."""
        if self.main_window.project:
            self._show_project_info()

    def on_leave(self) -> None:
        """离开页面."""
        pass

