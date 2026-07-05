"""分轨页面 / Separation Page.

配置分轨策略和设备，执行分轨，展示 Stem 结果。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QGroupBox,
    QFormLayout, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGridLayout, QScrollArea, QMessageBox,
    QSizePolicy, QApplication,
)
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices

from src.core.separation.audio_separator_runner import StemSeparator

if TYPE_CHECKING:
    from src.gui.windows.main_window import MainWindow


class SeparationPage(QWidget):
    """分轨页面 / Stem separation page."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._worker: QThread | None = None
        self._running = False
        self._stem_labels: dict[str, QLabel] = {}
        self._stem_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}
        self._stem_paths: dict[str, Path | None] = {}

        strategies = StemSeparator.get_available_strategies()
        self._strategy_keys = list(strategies.keys())
        self._strategy_names = [v["name"] for v in strategies.values()]

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("🎛️  音频分轨")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("使用 AI 模型将混音音频分离为独立乐器轨")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # === 设置区域 ===
        settings = QGroupBox("⚙️  分轨设置")
        form = QFormLayout(settings)
        form.setSpacing(12)

        # 策略 (ComboBox)
        self.cb_strategy = QComboBox()
        self.cb_strategy.addItems(self._strategy_names)
        form.addRow("分轨策略:", self.cb_strategy)

        # 设备 (ComboBox)
        self.cb_device = QComboBox()
        self.cb_device.addItems(["auto", "cuda", "cpu"])
        form.addRow("计算设备:", self.cb_device)

        # Shift 增强 (with description)
        shift_row = QHBoxLayout()
        self.spin_shifts = QSpinBox()
        self.spin_shifts.setRange(0, 10)
        self.spin_shifts.setValue(1)
        self.spin_shifts.setToolTip("多次随机位移推理后取平均, 消除伪影")
        shift_hint = QLabel("(范围: 0-10, 越大质量越好但越慢, 推荐 1)")
        shift_hint.setObjectName("hint_label")
        shift_hint.setStyleSheet("color: #8B7B9E; font-size: 12px;")
        shift_row.addWidget(self.spin_shifts)
        shift_row.addWidget(shift_hint)
        shift_row.addStretch()
        form.addRow("Shift 增强:", shift_row)

        # Overlap (with description)
        overlap_row = QHBoxLayout()
        self.spin_overlap = QDoubleSpinBox()
        self.spin_overlap.setRange(0, 0.99)
        self.spin_overlap.setValue(0.25)
        self.spin_overlap.setSingleStep(0.05)
        self.spin_overlap.setToolTip("音频分段处理时相邻段之间的重叠比例, 减少接缝伪影")
        overlap_hint = QLabel("(范围: 0-0.99, 段间重叠比例, 减少接缝咔嗒声, 推荐 0.25)")
        overlap_hint.setObjectName("hint_label")
        overlap_hint.setStyleSheet("color: #8B7B9E; font-size: 12px;")
        overlap_row.addWidget(self.spin_overlap)
        overlap_row.addWidget(overlap_hint)
        overlap_row.addStretch()
        form.addRow("重叠度:", overlap_row)

        # MP3 输出
        self.cb_mp3 = QCheckBox("输出 MP3 格式 (默认 WAV)")
        form.addRow("", self.cb_mp3)

        layout.addWidget(settings)

        # 运行按钮
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶️  开始分轨")
        self.btn_run.setProperty("primary", True)
        self.btn_run.setFixedWidth(160)
        self.btn_run.clicked.connect(self._run_separation)
        btn_row.addWidget(self.btn_run)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # === 结果区域 ===
        results_group = QGroupBox("📦 分轨结果")
        self.results_grid = QGridLayout(results_group)
        self.results_grid.setSpacing(12)

        # 6 轨占位
        stem_info = StemSeparator.get_stem_info("htdemucs_6s")
        positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
        for (name, zh), (row, col) in zip(stem_info.items(), positions):
            card = self._create_stem_card(name, zh)
            self.results_grid.addWidget(card, row, col)

        layout.addWidget(results_group)

        layout.addStretch()

    def _create_stem_card(self, name: str, zh_name: str) -> QFrame:
        """创建 Stem 信息卡片 / Create stem info card with action buttons."""
        card = QFrame()
        card.setObjectName("stem_card")
        card.setStyleSheet("""
            QFrame#stem_card {
                background-color: #1A1128;
                border: 1px solid #2D2045;
                border-radius: 8px;
                padding: 12px;
                min-height: 80px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)

        # 标题行: 名称 + 快捷按钮
        title_row = QHBoxLayout()
        title_label = QLabel(f"{zh_name}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E8E0F0;")
        title_row.addWidget(title_label)
        title_row.addStretch()

        # 打开文件夹按钮
        btn_open = QPushButton("📂 打开")
        btn_open.setFixedSize(64, 22)
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: #2D2045; color: #C8B8E0; border: 1px solid #3D3055;
                border-radius: 4px; font-size: 11px; padding: 2px 6px;
            }
            QPushButton:hover { background-color: #3D3055; color: #E8E0F0; }
        """)
        btn_open.setToolTip(f"在 Finder 中显示 {zh_name} 文件")
        btn_open.setVisible(False)
        title_row.addWidget(btn_open)

        # 复制路径按钮
        btn_copy = QPushButton("📋 复制")
        btn_copy.setFixedSize(64, 22)
        btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #2D2045; color: #C8B8E0; border: 1px solid #3D3055;
                border-radius: 4px; font-size: 11px; padding: 2px 6px;
            }
            QPushButton:hover { background-color: #3D3055; color: #E8E0F0; }
        """)
        btn_copy.setToolTip(f"复制 {zh_name} 文件路径到剪贴板")
        btn_copy.setVisible(False)
        title_row.addWidget(btn_copy)

        card_layout.addLayout(title_row)

        # 状态标签
        status_label = QLabel("等待中...")
        status_label.setObjectName("info_label")
        status_label.setStyleSheet("color: #8B7B9E; font-size: 12px;")
        card_layout.addWidget(status_label)

        self._stem_labels[name] = status_label
        self._stem_buttons[name] = (btn_open, btn_copy)

        # 绑定按钮事件
        stem_name = name  # capture for closure
        btn_open.clicked.connect(lambda checked=False, n=stem_name: self._open_stem_file(n))
        btn_copy.clicked.connect(lambda checked=False, n=stem_name: self._copy_stem_path(n))

        return card

    # ===== 执行分轨 =====

    def _run_separation(self) -> None:
        """执行分轨."""
        project = self.main_window.project
        if not project or not project.input_file:
            QMessageBox.warning(self, "提示", "请先在「项目」页创建或加载项目。")
            return

        if self._running:
            return

        from src.gui.workers.separation_worker import SeparationWorker

        strategy = self._strategy_keys[self.cb_strategy.currentIndex()]
        device = self.cb_device.currentText()
        shifts = self.spin_shifts.value()
        overlap = self.spin_overlap.value()
        mp3 = self.cb_mp3.isChecked()

        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_run.setText("⏳ 分轨中...")
        self.main_window.set_status("正在分轨...", 0)

        # 重置 stem 显示
        for label in self._stem_labels.values():
            label.setText("等待中...")

        self._worker = SeparationWorker(
            project=project,
            strategy=strategy,
            device=device,
            shifts=shifts,
            overlap=overlap,
            mp3=mp3,
        )

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_progress(self, pct: int, msg: str) -> None:
        """进度更新."""
        self.main_window.set_status(msg, pct)

    def _on_finished(self, stems: dict[str, Path]) -> None:
        """分轨完成."""
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重新分轨")

        # 更新项目状态
        project = self.main_window.project
        for name, path in stems.items():
            if name in project.stems:
                project.stems[name].path = path
        project.save()

        # 更新 Stem 显示
        stem_info = StemSeparator.get_stem_info("htdemucs_6s")
        for name, path in stems.items():
            zh = stem_info.get(name, name)
            size_mb = path.stat().st_size / (1024 * 1024)
            label = self._stem_labels.get(name)
            if label:
                label.setText(f"✅ {path.name}\n{size_mb:.1f} MB")

            # 保存路径并显示按钮
            self._stem_paths[name] = path
            btn_open, btn_copy = self._stem_buttons.get(name, (None, None))
            if btn_open:
                btn_open.setVisible(True)
            if btn_copy:
                btn_copy.setVisible(True)

        self.main_window.set_status("分轨完成!", 100)

        # 清理
        self._thread.quit()
        self._thread.wait()

    def _on_error(self, msg: str) -> None:
        """分轨出错."""
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重试")
        self.main_window.set_status(f"分轨失败: {msg}")
        QMessageBox.critical(self, "分轨失败", msg)

        self._thread.quit()
        self._thread.wait()

    # ===== Stem 操作按钮 / Stem action buttons =====

    def _open_stem_file(self, name: str) -> None:
        """在 Finder 中打开 stem 文件 / Reveal stem file in Finder."""
        path = self._stem_paths.get(name)
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        else:
            QMessageBox.information(self, "提示", f"「{name}」尚未生成分轨文件。")

    def _copy_stem_path(self, name: str) -> None:
        """复制 stem 路径到剪贴板 / Copy stem path to clipboard."""
        path = self._stem_paths.get(name)
        if path and path.exists():
            QApplication.clipboard().setText(str(path))
            self.main_window.set_status(f"已复制: {path.name}")
        else:
            QMessageBox.information(self, "提示", f"「{name}」尚未生成分轨文件。")

    # ===== 生命周期 =====

    def on_enter(self) -> None:
        """进入页面时刷新."""
        project = self.main_window.project
        if project:
            stem_info = StemSeparator.get_stem_info("htdemucs_6s")
            for name, label in self._stem_labels.items():
                stem = project.stems.get(name)
                btn_open, btn_copy = self._stem_buttons.get(name, (None, None))
                if stem and stem.path and stem.path.exists():
                    size_mb = stem.path.stat().st_size / (1024 * 1024)
                    label.setText(f"✅ {stem.path.name}\n{size_mb:.1f} MB")
                    self._stem_paths[name] = stem.path
                    if btn_open:
                        btn_open.setVisible(True)
                    if btn_copy:
                        btn_copy.setVisible(True)
                else:
                    zh = stem_info.get(name, name)
                    label.setText(f"{zh}\n等待中...")
                    if btn_open:
                        btn_open.setVisible(False)
                    if btn_copy:
                        btn_copy.setVisible(False)

    def on_leave(self) -> None:
        """离开页面."""
        pass

