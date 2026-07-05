"""音色匹配页面 / Timbre Matching Page.

Phase 4 — 从分离出的旋律 stem 提取音色特征，匹配最佳合成器预设，
并输出 Serum / Vital / General MIDI 等合成器可用参数。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QSpinBox, QScrollArea, QFrame, QMessageBox,
    QGridLayout, QApplication,
)
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices

from src.core.separation.audio_separator_runner import StemSeparator

if TYPE_CHECKING:
    from src.gui.windows.main_window import MainWindow

MELODIC_STEMS = ["piano", "guitar", "bass", "vocals"]
MELODIC_STEMS_ZH = {
    "piano": "钢琴 Piano", "guitar": "吉他 Guitar",
    "bass": "贝斯 Bass", "vocals": "人声 Vocals",
}


class TimbrePage(QWidget):
    """音色匹配页面 / Timbre matching page."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._worker: QThread | None = None
        self._running = False
        self._match_cards: list[QFrame] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("🎸 音色预设匹配")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("提取音色特征 → 匹配预设 → 输出 Serum/Vital/GM 合成器参数")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # === 设置区域 ===
        settings = QGroupBox("⚙️  匹配设置")
        form = QFormLayout(settings)
        form.setSpacing(12)

        self.cb_stem = QComboBox()
        form.addRow("目标 Stem:", self.cb_stem)

        self.spin_top_k = QSpinBox()
        self.spin_top_k.setRange(1, 20)
        self.spin_top_k.setValue(5)
        self.spin_top_k.setToolTip("返回匹配度最高的 K 个预设")
        form.addRow("返回数量 (Top-K):", self.spin_top_k)

        layout.addWidget(settings)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶️  开始匹配")
        self.btn_run.setProperty("primary", True)
        self.btn_run.setFixedWidth(160)
        self.btn_run.clicked.connect(self._run_matching)
        btn_row.addWidget(self.btn_run)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # === 结果区域 ===
        results_label = QLabel("📊 匹配结果 (点击展开合成器参数)")
        results_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #E8E0F0; margin-top: 8px;")
        layout.addWidget(results_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch()
        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll)

    # ===== 执行匹配 =====

    def _run_matching(self) -> None:
        """执行音色匹配."""
        project = self.main_window.project
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页创建或加载项目。")
            return

        if self._running:
            return

        stem_name = self.cb_stem.currentData()
        if not stem_name:
            QMessageBox.warning(self, "提示", "请选择目标 Stem。")
            return

        if not project.stems.get(stem_name) or not project.stems[stem_name].path:
            QMessageBox.warning(self, "提示", f"Stem \"{stem_name}\" 尚未分离，请先运行分轨。")
            return

        from src.gui.workers.timbre_worker import TimbreWorker

        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_run.setText("⏳ 匹配中...")
        self.main_window.set_status(f"正在分析 {MELODIC_STEMS_ZH.get(stem_name, stem_name)} 音色...", 0)

        self._clear_cards()

        self._worker = TimbreWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=stem_name,
            top_k=self.spin_top_k.value(),
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
        self.main_window.set_status(msg, pct)

    def _on_finished(self, results: dict[str, list[dict]]) -> None:
        """匹配完成."""
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重新匹配")

        self._clear_cards()

        for sname, matches in results.items():
            zh_name = MELODIC_STEMS_ZH.get(sname, sname)
            header = QLabel(f"  {zh_name}")
            header.setStyleSheet(
                "font-weight: bold; font-size: 15px; color: #C8B8E0; "
                "padding: 6px 0; border-bottom: 1px solid #2D2045;"
            )
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, header)

            if not matches:
                empty_label = QLabel("  无匹配结果")
                empty_label.setStyleSheet("color: #8B7B9E; font-size: 13px; padding: 4px 0;")
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, empty_label)
                continue

            for m in matches:
                card = self._create_result_card(m)
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
                self._match_cards.append(card)

        self.main_window.set_status("音色匹配完成!", 100)
        self._thread.quit()
        self._thread.wait()

    def _on_error(self, msg: str) -> None:
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重试")
        self.main_window.set_status(f"匹配失败: {msg}")
        QMessageBox.critical(self, "匹配失败", msg)
        self._thread.quit()
        self._thread.wait()

    # ===== 结果卡片 =====

    def _create_result_card(self, match: dict) -> QFrame:
        """创建带合成器参数的匹配结果卡片."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1A1128;
                border: 1px solid #2D2045;
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        card_layout.setContentsMargins(14, 12, 14, 12)

        # --- 顶部: 排名 + 信息 ---
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        rank = match.get("rank", "?")
        rank_label = QLabel(f"#{rank}")
        rank_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #A080D0; min-width: 50px;"
        )
        rank_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(rank_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        preset_name = match.get("preset_name", "未知预设")
        name_label = QLabel(preset_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #E8E0F0;")
        info_layout.addWidget(name_label)

        category = match.get("category", "")
        instrument = match.get("instrument", "")
        meta_parts = [p for p in [category, instrument] if p]
        meta_text = " · ".join(meta_parts) if meta_parts else "—"
        meta_label = QLabel(meta_text)
        meta_label.setStyleSheet("font-size: 12px; color: #8B7B9E;")
        info_layout.addWidget(meta_label)

        desc = match.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("font-size: 12px; color: #9B8FB0;")
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)

        tags = match.get("tags", [])
        if tags:
            tags_text = "🏷 " + " · ".join(tags[:6])
            tags_label = QLabel(tags_text)
            tags_label.setStyleSheet("font-size: 11px; color: #6B5B8E;")
            info_layout.addWidget(tags_label)

        top_row.addLayout(info_layout, stretch=1)

        # 得分
        score = match.get("score", 0.0)
        score_pct = int(score * 100)
        if score_pct >= 80:
            score_color = "#6EE07E"
        elif score_pct >= 50:
            score_color = "#E0C86E"
        else:
            score_color = "#E06E6E"

        score_label = QLabel(f"{score_pct}%")
        score_label.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {score_color}; min-width: 60px;"
        )
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(score_label)

        card_layout.addLayout(top_row)

        # --- 合成器参数展开区 ---
        synth_params = match.get("synth_params", {})
        if synth_params:
            # 展开/收起按钮
            toggle_btn = QPushButton("🔽 展开合成器参数 (Serum / Vital / General MIDI)")
            toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #221835;
                    color: #A090C0;
                    border: 1px solid #3D3055;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover { background-color: #2D2045; color: #E0D0F0; }
            """)
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            card_layout.addWidget(toggle_btn)

            # 参数详情容器 (初始隐藏)
            detail_frame = QFrame()
            detail_frame.setVisible(False)
            detail_frame.setStyleSheet("""
                QFrame {
                    background-color: #130D20;
                    border: 1px solid #2D2045;
                    border-radius: 6px;
                }
            """)
            detail_layout = QVBoxLayout(detail_frame)
            detail_layout.setSpacing(6)
            detail_layout.setContentsMargins(10, 8, 10, 8)

            # Serum 参数
            serum = synth_params.get("serum", {})
            if serum:
                detail_layout.addWidget(self._make_synth_section("🔴 Xfer Serum", serum))

            # Vital 参数
            vital = synth_params.get("vital", {})
            if vital:
                detail_layout.addWidget(self._make_synth_section("🟠 Vital", vital))

            # General MIDI 参数
            gm = synth_params.get("general_midi", {})
            if gm:
                detail_layout.addWidget(self._make_synth_section("🟢 General MIDI", gm))

            card_layout.addWidget(detail_frame)

            # 绑定展开/收起
            toggle_btn.clicked.connect(
                lambda checked=False, b=toggle_btn, d=detail_frame:
                self._toggle_synth_params(b, d)
            )

        return card

    def _make_synth_section(self, title: str, params: dict) -> QFrame:
        """创建单个合成器的参数子区域."""
        section = QFrame()
        section.setStyleSheet("""
            QFrame { background: transparent; border: none; }
        """)
        slayout = QVBoxLayout(section)
        slayout.setSpacing(4)
        slayout.setContentsMargins(4, 4, 4, 4)

        header = QLabel(title)
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #D0C0E8;")
        slayout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnMinimumWidth(1, 130)

        row = 0
        col = 0
        MAX_ROWS = 10

        # 遍历嵌套字典，展平为 key: value 对
        flat_items = self._flatten_params(params, max_items=20)

        for key, value in flat_items:
            if row >= MAX_ROWS:
                break
            key_label = QLabel(key)
            key_label.setStyleSheet("font-size: 11px; color: #8B7B9E; font-family: monospace;")
            val_label = QLabel(str(value))
            val_label.setStyleSheet("font-size: 11px; color: #C8B8E0; font-family: monospace;")
            grid.addWidget(key_label, row, col * 2)
            grid.addWidget(val_label, row, col * 2 + 1)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        slayout.addLayout(grid)
        return section

    def _flatten_params(self, d: dict, prefix: str = "", max_items: int = 20) -> list[tuple[str, str]]:
        """将嵌套字典展平为 (label, value) 列表."""
        items = []
        for key, value in d.items():
            if key == "synth":
                continue  # 跳过 synth 名
            full_key = f"{prefix}{key}" if prefix else key
            if isinstance(value, dict) and len(value) <= 6:
                # 小字典 → 展平
                for sub_k, sub_v in value.items():
                    items.append((f"{full_key}.{sub_k}", str(sub_v)))
            elif isinstance(value, dict):
                items.append((full_key, "..."))
            else:
                items.append((full_key, str(value)))
            if len(items) >= max_items:
                break
        return items

    @staticmethod
    def _toggle_synth_params(btn: QPushButton, detail: QFrame) -> None:
        """展开/收起合成器参数."""
        visible = not detail.isVisible()
        detail.setVisible(visible)
        if visible:
            btn.setText("🔼 收起合成器参数")
        else:
            btn.setText("🔽 展开合成器参数 (Serum / Vital / General MIDI)")

    def _clear_cards(self) -> None:
        """清除所有结果卡片."""
        for card in self._match_cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._match_cards.clear()
        while self._cards_layout.count() > 1:
            item = self._cards_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
            self._cards_layout.removeItem(item)

    # ===== 生命周期 =====

    def on_enter(self) -> None:
        """进入页面时刷新 Stem 列表."""
        project = self.main_window.project
        self.cb_stem.clear()

        if not project:
            return

        stem_info = StemSeparator.get_stem_info("htdemucs_6s")
        for sname in MELODIC_STEMS:
            stem = project.stems.get(sname)
            if stem:
                has_data = stem.path and stem.path.exists() if stem.path else False
                status = "✅" if has_data else "⏳"
                zh = stem_info.get(sname, sname)
                label = f"{status} {zh} ({sname})"
                self.cb_stem.addItem(label, sname)

        self._clear_cards()
        for sname in MELODIC_STEMS:
            stem = project.stems.get(sname)
            if stem and stem.matched_presets:
                self._display_cached_results(sname, stem.matched_presets)

    def _display_cached_results(self, sname: str, matches: list[dict]) -> None:
        """显示缓存的匹配结果."""
        zh_name = MELODIC_STEMS_ZH.get(sname, sname)
        header = QLabel(f"  {zh_name} (缓存)")
        header.setStyleSheet(
            "font-weight: bold; font-size: 15px; color: #C8B8E0; "
            "padding: 6px 0; border-bottom: 1px solid #2D2045;"
        )
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, header)

        for m in matches:
            card = self._create_result_card(m)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            self._match_cards.append(card)

    def on_leave(self) -> None:
        pass
