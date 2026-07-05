"""自定义控件模块 / Custom widgets module.

参考 UI 设计规范，实现深紫科技风自定义控件。
"""

from src.gui.widgets.progress_bar import GradientProgressBar
from src.gui.widgets.stem_panel import StemPanel
from src.gui.widgets.waveform_placeholder import WaveformPlaceholder
from src.gui.widgets.status_indicator import StatusIndicator
from src.gui.widgets.collapsible_section import CollapsibleSection
from src.gui.widgets.file_drop_area import FileDropArea

__all__ = [
    "GradientProgressBar",
    "StemPanel",
    "WaveformPlaceholder",
    "StatusIndicator",
    "CollapsibleSection",
    "FileDropArea",
]

