"""深紫科技风 QSS 样式表 / Dark Purple Tech QSS Stylesheet.

所有颜色通过 generate_stylesheet() 函数生成为 Python 字符串。
无需外部 .qss 文件，便于 PyInstaller 打包和主题切换。
"""

from __future__ import annotations

# ===== 颜色令牌 / Color Tokens =====
COLORS = {
    "primary": "#7C3AED",
    "primary_light": "#A78BFA",
    "primary_pale": "#C4B5FD",
    "primary_dark": "#5B21B6",
    "bg_dark": "#0F0A1A",
    "bg_panel": "#1A1128",
    "bg_surface": "#231840",
    "bg_hover": "#2D1F50",
    "accent": "#00F5FF",
    "accent_dim": "#0099AA",
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "text_primary": "#E8E0F0",
    "text_secondary": "#9B8FB0",
    "text_disabled": "#5A5070",
    "border": "#2D2045",
    "border_focus": "#7C3AED",
}


def generate_stylesheet() -> str:
    """生成完整的 QSS 样式表字符串 / Generate full QSS stylesheet.

    Returns:
        可直接应用到 QApplication 的 QSS 字符串
    """
    c = COLORS

    return f"""/* ===== UMuse — 深紫科技风主题 / Dark Purple Tech Theme ===== */

/* --- 全局 / Global --- */
QWidget {{
    background-color: {c["bg_dark"]};
    color: {c["text_primary"]};
    font-family: "PingFang SC", "Segoe UI", "Noto Sans SC", sans-serif;
    font-size: 13px;
}}

/* --- 主窗口 / Main Window --- */
QMainWindow {{
    background-color: {c["bg_dark"]};
}}

QMainWindow::separator {{
    width: 1px;
    background-color: {c["border"]};
}}

/* --- 侧边栏 / Sidebar --- */
QWidget#sidebar {{
    background-color: {c["bg_panel"]};
    border-right: 1px solid {c["border"]};
    min-width: 180px;
    max-width: 180px;
}}

QWidget#sidebar QLabel#logo {{
    color: {c["primary_light"]};
    font-size: 20px;
    font-weight: bold;
    padding: 20px 16px 16px 16px;
}}

QWidget#sidebar QLabel#version {{
    color: {c["text_disabled"]};
    font-size: 11px;
    padding: 8px 16px;
}}

/* 导航按钮 / Nav Button */
QPushButton[nav="true"] {{
    background: transparent;
    color: {c["text_secondary"]};
    border: none;
    border-left: 3px solid transparent;
    text-align: left;
    padding: 10px 16px 10px 13px;
    font-size: 13px;
    min-height: 20px;
}}

QPushButton[nav="true"]:hover {{
    background-color: {c["bg_surface"]};
    color: {c["text_primary"]};
    border-left: 3px solid {c["primary_light"]};
}}

QPushButton[nav="true"][selected="true"] {{
    background-color: {c["bg_surface"]};
    color: {c["primary_light"]};
    border-left: 3px solid {c["primary"]};
    font-weight: bold;
}}

/* 设置按钮 / Settings Button */
QPushButton#btn_settings {{
    background: transparent;
    color: {c["text_secondary"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    margin: 8px 12px;
}}

QPushButton#btn_settings:hover {{
    background-color: {c["bg_surface"]};
    color: {c["text_primary"]};
    border-color: {c["primary_light"]};
}}

/* --- 内容区标题 / Content Header --- */
QLabel#page_title {{
    font-size: 22px;
    font-weight: bold;
    color: {c["text_primary"]};
    padding: 20px 24px 4px 24px;
}}

QLabel#page_subtitle {{
    font-size: 13px;
    color: {c["text_secondary"]};
    padding: 0px 24px 16px 24px;
}}

/* --- 按钮 / Buttons --- */
QPushButton {{
    background-color: {c["bg_surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {c["bg_hover"]};
    border-color: {c["primary_light"]};
}}

QPushButton:pressed {{
    background-color: {c["primary_dark"]};
}}

QPushButton:disabled {{
    background-color: {c["bg_panel"]};
    color: {c["text_disabled"]};
    border-color: {c["border"]};
}}

/* 主操作按钮 / Primary Button */
QPushButton[primary="true"] {{
    background-color: {c["primary"]};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 28px;
    font-weight: bold;
    font-size: 14px;
}}

QPushButton[primary="true"]:hover {{
    background-color: {c["primary_light"]};
}}

QPushButton[primary="true"]:pressed {{
    background-color: {c["primary_dark"]};
}}

QPushButton[primary="true"]:disabled {{
    background-color: {c["bg_surface"]};
    color: {c["text_disabled"]};
}}

/* --- 输入框 / Input Fields --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {c["bg_surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 20px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {c["primary"]};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {c["text_secondary"]};
    margin-right: 4px;
}}

QComboBox QAbstractItemView {{
    background-color: {c["bg_surface"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["primary"]};
    selection-color: white;
    outline: none;
}}

/* --- 进度条 / Progress Bar --- */
QProgressBar {{
    background-color: {c["bg_surface"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    text-align: center;
    color: {c["text_primary"]};
    font-size: 11px;
    min-height: 16px;
    max-height: 16px;
}}

QProgressBar::chunk {{
    background-color: {c["accent_dim"]};
    border-radius: 3px;
}}

/* --- 分组框 / Group Box --- */
QGroupBox {{
    background-color: {c["bg_panel"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    margin-top: 16px;
    padding: 16px 16px 12px 16px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {c["text_primary"]};
}}

/* --- 表格 / Table --- */
QTableWidget, QTableWidget {{
    background-color: {c["bg_panel"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    gridline-color: {c["border"]};
    selection-background-color: {c["bg_surface"]};
    selection-color: {c["text_primary"]};
}}

QTableWidget::item {{
    padding: 6px 10px;
}}

QHeaderView::section {{
    background-color: {c["bg_surface"]};
    color: {c["text_secondary"]};
    border: none;
    border-bottom: 1px solid {c["border"]};
    padding: 8px 10px;
    font-weight: bold;
    font-size: 12px;
}}

/* --- 滚动条 / Scrollbar --- */
QScrollBar:vertical {{
    background: {c["bg_dark"]};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {c["bg_hover"]};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c["text_disabled"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {c["bg_dark"]};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {c["bg_hover"]};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* --- 标签页 / Tab Widget --- */
QTabWidget::pane {{
    border: 1px solid {c["border"]};
    border-radius: 6px;
    background-color: {c["bg_panel"]};
}}

QTabBar::tab {{
    background-color: {c["bg_dark"]};
    color: {c["text_secondary"]};
    border: 1px solid {c["border"]};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 20px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {c["bg_panel"]};
    color: {c["primary_light"]};
    border-bottom: 2px solid {c["primary"]};
}}

QTabBar::tab:hover {{
    color: {c["text_primary"]};
}}

/* --- 工具提示 / Tooltip --- */
QToolTip {{
    background-color: {c["bg_surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}

/* --- 状态栏 / Status Bar --- */
QStatusBar {{
    background-color: {c["bg_panel"]};
    border-top: 1px solid {c["border"]};
    color: {c["text_secondary"]};
    font-size: 12px;
    padding: 4px 12px;
    min-height: 28px;
}}

QStatusBar QLabel {{
    color: {c["text_secondary"]};
    background: transparent;
    padding: 0 8px;
}}

/* --- 菜单 / Menu --- */
QMenu {{
    background-color: {c["bg_surface"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 28px 6px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {c["primary"]};
}}

QMenu::separator {{
    height: 1px;
    background: {c["border"]};
    margin: 4px 8px;
}}

/* --- 复选框 / Checkbox & Radio --- */
QCheckBox, QRadioButton {{
    color: {c["text_primary"]};
    spacing: 8px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {c["text_disabled"]};
    border-radius: 3px;
    background: {c["bg_surface"]};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {c["primary"]};
    border-color: {c["primary"]};
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {c["primary_light"]};
}}

/* --- 分割线 / Splitter --- */
QSplitter::handle {{
    background-color: {c["border"]};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

/* --- 标签 / Label --- */
QLabel {{
    background: transparent;
    color: {c["text_primary"]};
}}

QLabel#info_label {{
    color: {c["text_secondary"]};
    font-size: 12px;
}}

/* --- 列表 / List --- */
QListWidget {{
    background-color: {c["bg_panel"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 12px;
    border-radius: 4px;
}}

QListWidget::item:selected {{
    background-color: {c["bg_surface"]};
    color: {c["primary_light"]};
}}

QListWidget::item:hover {{
    background-color: {c["bg_hover"]};
}}
"""

