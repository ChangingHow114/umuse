"""效果器参数预估页面 / Effects Analysis Page.

Phase 5 — 对比干/湿音频，估算 EQ、混响、压缩等效果器参数。
支持 Phase 4→5→4 迭代精炼。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QScrollArea, QFrame,
    QMessageBox, QGridLayout, QApplication,
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


class EffectsPage(QWidget):
    """效果器参数预估页面 / Effects analysis page."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__()
        self.main_window = main_window
        self._worker: QThread | None = None
        self._running = False
        self._result_cards: list[QFrame] = []
        self._effects_paths: dict[str, Path | None] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("🎚️  效果器参数预估")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("基于 Phase 4 匹配到的干音预设，逆向估算混音中使用的 EQ、混响、压缩参数")
        subtitle.setObjectName("page_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # === 设置区域 ===
        settings = QGroupBox("⚙️  分析设置")
        form = QFormLayout(settings)
        form.setSpacing(12)

        # Stem 选择
        self.cb_stem = QComboBox()
        form.addRow("目标 Stem:", self.cb_stem)

        # 精炼模式
        self.cb_refine = QCheckBox("使用迭代精炼 (Phase 4→5→4 联动, 更准确但更慢)")
        self.cb_refine.setChecked(True)
        self.cb_refine.setToolTip(
            "开启后: 第一轮粗匹配 → 效果器估算 → 特征补偿 → 第二轮精匹配\n"
            "关闭后: 仅运行独立效果器分析 (需已有匹配结果)"
        )
        form.addRow("", self.cb_refine)

        # 最大迭代次数
        iter_row = QHBoxLayout()
        self.spin_iterations = QSpinBox()
        self.spin_iterations.setRange(1, 5)
        self.spin_iterations.setValue(3)
        self.spin_iterations.setToolTip("迭代精炼最大轮数 (通常 2-3 轮收敛)")
        iter_hint = QLabel("(范围: 1-5, 越多越慢, 推荐 3)")
        iter_hint.setStyleSheet("color: #8B7B9E; font-size: 12px;")
        iter_row.addWidget(self.spin_iterations)
        iter_row.addWidget(iter_hint)
        iter_row.addStretch()
        form.addRow("最大迭代轮数:", iter_row)

        # 联动: refinement checkbox 控制 iterations spinner
        self.cb_refine.toggled.connect(self.spin_iterations.setEnabled)

        layout.addWidget(settings)

        # 运行按钮
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶️  开始分析")
        self.btn_run.setProperty("primary", True)
        self.btn_run.setFixedWidth(160)
        self.btn_run.clicked.connect(self._run_analysis)
        btn_row.addWidget(self.btn_run)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # === 结果区域 ===
        results_label = QLabel("📊 分析结果")
        results_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #E8E0F0; margin-top: 8px;")
        layout.addWidget(results_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch()
        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll)

    # ===== 执行分析 =====

    def _run_analysis(self) -> None:
        """执行效果器分析."""
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

        stem_info = project.stems.get(stem_name)
        if not stem_info or not stem_info.path:
            QMessageBox.warning(self, "提示", f"Stem \"{stem_name}\" 尚未分离，请先运行分轨。")
            return

        use_refinement = self.cb_refine.isChecked()
        if use_refinement and not stem_info.matched_presets:
            # 精炼模式需要先有匹配结果
            reply = QMessageBox.question(
                self, "需要匹配结果",
                f"「{MELODIC_STEMS_ZH.get(stem_name, stem_name)}」还没有音色匹配结果。\n\n"
                "迭代精炼需要先运行 Phase 4 匹配。\n"
                "是否先运行音色匹配?（匹配完成后将自动继续效果器分析）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_matching_then_effects(stem_name)
            return

        from src.gui.workers.effects_worker import EffectsWorker

        self._running = True
        self.btn_run.setEnabled(False)
        mode_text = "精炼分析" if use_refinement else "独立分析"
        self.btn_run.setText(f"⏳ {mode_text}中...")
        self.main_window.set_status(
            f"正在{mode_text} {MELODIC_STEMS_ZH.get(stem_name, stem_name)}...", 0
        )

        self._clear_cards()

        self._worker = EffectsWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=stem_name,
            use_refinement=use_refinement,
            max_iterations=self.spin_iterations.value(),
        )

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _run_matching_then_effects(self, stem_name: str) -> None:
        """先运行匹配, 完成后自动运行效果器分析."""
        from src.gui.workers.timbre_worker import TimbreWorker

        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_run.setText("⏳ 先匹配中...")
        self.main_window.set_status(f"先运行音色匹配 ({stem_name})...", 0)

        self._pending_effects = True
        self._pending_stem = stem_name

        self._worker = TimbreWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=stem_name,
            top_k=5,
        )

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_matching_done_then_effects)
        self._worker.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_matching_done_then_effects(self, results: dict) -> None:
        """匹配完成后启动效果器分析."""
        self._thread.quit()
        self._thread.wait()

        stem_name = getattr(self, '_pending_stem', None)
        if not stem_name:
            return

        from src.gui.workers.effects_worker import EffectsWorker

        self.btn_run.setText("⏳ 精炼分析中...")
        self.main_window.set_status(f"匹配完成, 开始效果器精炼 ({stem_name})...", 30)

        self._worker = EffectsWorker(
            pipeline_manager=self.main_window.pipeline_manager,
            stem_name=stem_name,
            use_refinement=True,
            max_iterations=self.spin_iterations.value(),
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

    def _on_finished(self, data: dict) -> None:
        """分析完成."""
        self._running = False
        self.btn_run.setEnabled(True)
        mode = data.get("mode", "effects_only")
        results = data.get("results", {})

        if mode == "refinement":
            self.btn_run.setText("▶️  重新精炼")
        else:
            self.btn_run.setText("▶️  重新分析")

        self._clear_cards()

        for sname, result in results.items():
            zh_name = MELODIC_STEMS_ZH.get(sname, sname)

            if mode == "refinement":
                self._build_refinement_cards(sname, zh_name, result)
            else:
                self._build_effects_card(sname, zh_name, result)

        self.main_window.set_status("效果器分析完成!", 100)
        self._thread.quit()
        self._thread.wait()

    def _on_error(self, msg: str) -> None:
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶️  重试")
        self.main_window.set_status(f"分析失败: {msg}")
        QMessageBox.critical(self, "分析失败", msg)
        self._thread.quit()
        self._thread.wait()

    # ===== 结果卡片构建 =====

    def _build_refinement_cards(self, sname: str, zh_name: str, result: dict) -> None:
        """构建精炼结果卡片组."""
        # 迭代摘要卡片
        iterations = result.get("iterations", 0)
        converged = result.get("converged", False)
        score_improvement = result.get("score_improvement", 0.0)
        score_history = result.get("score_history", [])
        preset_history = result.get("preset_history", [])

        summary_card = self._make_section_card(
            f"🔄 {zh_name} — 迭代精炼摘要",
            [
                f"迭代轮数: {iterations}  |  收敛: {'✅ 是' if converged else '⚠️ 否'}",
                f"得分提升: {score_improvement:+.4f}",
                f"得分历程: {' → '.join(f'{s:.3f}' for s in score_history)}" if score_history else "",
                f"预设历程: {' → '.join(preset_history)}" if preset_history else "",
            ],
            "#2D2045",
        )
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, summary_card)

        # 初始 vs 精炼匹配对比
        initial = result.get("initial_matches", [])
        refined = result.get("refined_matches", [])
        if initial and refined:
            compare_card = self._make_comparison_card(initial[:3], refined[:3])
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, compare_card)

        # 效果器参数详情
        effects = result.get("effects_profile")
        if effects:
            effects_card = self._make_effects_detail_card(effects)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, effects_card)

    def _build_effects_card(self, sname: str, zh_name: str, profile: dict) -> None:
        """构建独立效果器分析结果卡片."""
        effects_card = self._make_effects_detail_card(profile, title_prefix=f"🎚️ {zh_name}")
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, effects_card)

    def _make_section_card(
        self, title: str, lines: list[str], border_color: str = "#2D2045"
    ) -> QFrame:
        """创建文本信息卡片."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1A1128;
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E8E0F0;")
        card_layout.addWidget(title_label)

        for line in lines:
            if not line:
                continue
            line_label = QLabel(line)
            line_label.setStyleSheet("font-size: 13px; color: #C8B8E0;")
            line_label.setWordWrap(True)
            card_layout.addWidget(line_label)

        return card

    def _make_comparison_card(
        self, initial: list[dict], refined: list[dict]
    ) -> QFrame:
        """创建匹配对比卡片."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1A1128;
                border: 1px solid #3D3055;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        title_label = QLabel("📊 匹配对比 (初始 → 精炼)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E8E0F0;")
        card_layout.addWidget(title_label)

        # 使用 GridLayout 对比
        grid = QGridLayout()
        grid.setSpacing(8)

        # 表头
        grid.addWidget(QLabel(""), 0, 0)
        header_initial = QLabel("🔸 初始匹配")
        header_initial.setStyleSheet("font-weight: bold; color: #E0C86E; font-size: 13px;")
        grid.addWidget(header_initial, 0, 1)
        header_refined = QLabel("🔹 精炼匹配")
        header_refined.setStyleSheet("font-weight: bold; color: #6EE07E; font-size: 13px;")
        grid.addWidget(header_refined, 0, 2)

        max_rows = max(len(initial), len(refined))
        for i in range(max_rows):
            rank_label = QLabel(f"#{i+1}")
            rank_label.setStyleSheet("font-size: 13px; color: #8B7B9E;")
            grid.addWidget(rank_label, i + 1, 0)

            if i < len(initial):
                im = initial[i]
                init_text = f"{im.get('preset_name', '?')} ({int(im.get('score', 0)*100)}%)"
                init_label = QLabel(init_text)
                init_label.setStyleSheet("font-size: 12px; color: #E0C86E;")
                grid.addWidget(init_label, i + 1, 1)
            else:
                grid.addWidget(QLabel("—"), i + 1, 1)

            if i < len(refined):
                rm = refined[i]
                ref_text = f"{rm.get('preset_name', '?')} ({int(rm.get('score', 0)*100)}%)"
                ref_label = QLabel(ref_text)
                ref_label.setStyleSheet("font-size: 12px; color: #6EE07E;")
                grid.addWidget(ref_label, i + 1, 2)
            else:
                grid.addWidget(QLabel("—"), i + 1, 2)

        card_layout.addLayout(grid)
        return card

    def _make_effects_detail_card(
        self, profile: dict, title_prefix: str = "🎚️ 效果器参数"
    ) -> QFrame:
        """创建效果器参数详情卡片."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1A1128;
                border: 1px solid #4A3060;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        stem_name = profile.get("stem_name", "")
        preset_name = profile.get("preset_name", "")
        confidence = profile.get("confidence", 0.0)
        title_text = f"{title_prefix} — {stem_name}"
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E8E0F0;")
        card_layout.addWidget(title_label)

        if preset_name:
            preset_label = QLabel(f"参考预设: {preset_name}")
            preset_label.setStyleSheet("font-size: 12px; color: #9B8FB0;")
            card_layout.addWidget(preset_label)

        conf_color = "#6EE07E" if confidence >= 0.5 else "#E0C86E" if confidence >= 0.3 else "#E06E6E"
        conf_label = QLabel(f"置信度: {confidence:.2f}")
        conf_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {conf_color};")
        card_layout.addWidget(conf_label)

        # === EQ 参数 ===
        eq = profile.get("eq", {})
        if eq:
            eq_section = QLabel("🎛 EQ 参数")
            eq_section.setStyleSheet(
                "font-weight: bold; font-size: 13px; color: #C8B8E0; "
                "margin-top: 6px; padding-top: 6px; border-top: 1px solid #2D2045;"
            )
            card_layout.addWidget(eq_section)

            bands = eq.get("bands", [])
            if bands:
                for i, band in enumerate(bands):
                    freq = band.get("freq_hz", 0)
                    gain = band.get("gain_db", 0)
                    q = band.get("q", 1.0)
                    gain_sign = "+" if gain >= 0 else ""
                    band_text = f"  Band {i+1}: {freq:.0f} Hz  |  {gain_sign}{gain:.1f} dB  |  Q={q:.2f}"
                    band_label = QLabel(band_text)
                    gain_color = "#6EE07E" if gain > 0 else "#E06E6E" if gain < 0 else "#8B7B9E"
                    band_label.setStyleSheet(f"font-size: 12px; color: {gain_color}; font-family: monospace;")
                    card_layout.addWidget(band_label)
            else:
                card_layout.addWidget(QLabel("  (无明显 EQ 处理)"))

        # === 混响参数 ===
        reverb = profile.get("reverb", {})
        if reverb:
            rev_section = QLabel("🌊 混响参数")
            rev_section.setStyleSheet(
                "font-weight: bold; font-size: 13px; color: #C8B8E0; "
                "margin-top: 6px; padding-top: 6px; border-top: 1px solid #2D2045;"
            )
            card_layout.addWidget(rev_section)

            rt60 = reverb.get("rt60_sec", 0)
            dry_wet = reverb.get("dry_wet_ratio", 0)
            rev_text = f"  RT60: {rt60:.2f}s  |  Dry/Wet: {dry_wet:.2f}"
            rev_label = QLabel(rev_text)
            rev_label.setStyleSheet("font-size: 12px; color: #B8D0E0; font-family: monospace;")
            card_layout.addWidget(rev_label)

        # === 压缩参数 ===
        comp = profile.get("compression", {})
        if comp:
            comp_section = QLabel("📉 压缩参数")
            comp_section.setStyleSheet(
                "font-weight: bold; font-size: 13px; color: #C8B8E0; "
                "margin-top: 6px; padding-top: 6px; border-top: 1px solid #2D2045;"
            )
            card_layout.addWidget(comp_section)

            threshold = comp.get("threshold_db", 0)
            ratio = comp.get("ratio", 1.0)
            attack = comp.get("attack_ms", 0)
            release = comp.get("release_ms", 0)
            comp_text = (
                f"  Threshold: {threshold:.1f} dB  |  Ratio: {ratio:.1f}:1\n"
                f"  Attack: {attack:.1f} ms  |  Release: {release:.1f} ms"
            )
            comp_label = QLabel(comp_text)
            comp_label.setStyleSheet("font-size: 12px; color: #E0C8B0; font-family: monospace;")
            card_layout.addWidget(comp_label)

        # === 底部: JSON 路径 + 操作按钮 ===
        effects_path = self._effects_paths.get(stem_name)
        if effects_path and effects_path.exists():
            btn_row = QHBoxLayout()
            btn_open = QPushButton("📂 打开 JSON")
            btn_open.setFixedSize(100, 24)
            btn_open.setStyleSheet("""
                QPushButton {
                    background-color: #2D2045; color: #C8B8E0; border: 1px solid #3D3055;
                    border-radius: 4px; font-size: 11px;
                }
                QPushButton:hover { background-color: #3D3055; }
            """)
            btn_open.clicked.connect(lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(effects_path.parent))
            ))

            btn_copy = QPushButton("📋 复制路径")
            btn_copy.setFixedSize(100, 24)
            btn_copy.setStyleSheet("""
                QPushButton {
                    background-color: #2D2045; color: #C8B8E0; border: 1px solid #3D3055;
                    border-radius: 4px; font-size: 11px;
                }
                QPushButton:hover { background-color: #3D3055; }
            """)
            btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(str(effects_path)))

            btn_row.addWidget(btn_open)
            btn_row.addWidget(btn_copy)
            btn_row.addStretch()
            card_layout.addLayout(btn_row)

            path_label = QLabel(str(effects_path))
            path_label.setStyleSheet("font-size: 11px; color: #5A5070;")
            card_layout.addWidget(path_label)

        return card

    def _clear_cards(self) -> None:
        """清除所有结果卡片."""
        for card in self._result_cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._result_cards.clear()
        while self._cards_layout.count() > 1:
            item = self._cards_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
            self._cards_layout.removeItem(item)
        self._effects_paths.clear()

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
                has_match = bool(stem.matched_presets) if stem else False
                status = "✅" if has_data else "⏳"
                match_status = " [已匹配]" if has_match else ""
                zh = stem_info.get(sname, sname)
                label = f"{status} {zh} ({sname}){match_status}"
                self.cb_stem.addItem(label, sname)

        # 检查缓存的 effects JSON
        if project and project.output_dir:
            for sname in MELODIC_STEMS:
                effects_path = project.output_dir / sname / "effects_params.json"
                if effects_path.exists():
                    self._effects_paths[sname] = effects_path

    def on_leave(self) -> None:
        pass
