"""LilyPond 导出与编译引擎 / LilyPond export and compilation engine.

管理 LilyPond 模板、选项配置、.ly 文件导出和 PDF/PNG 编译。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


# ===== LilyPond 配置 =====

# LilyPond 可执行文件路径 (由 music21 配置，这里作为 fallback)
_LILYPOND_PATH: Path | None = None


def get_lilypond_path() -> Path:
    """获取 LilyPond 可执行文件路径 / Get LilyPond executable path."""
    global _LILYPOND_PATH

    if _LILYPOND_PATH and _LILYPOND_PATH.exists():
        return _LILYPOND_PATH

    # 从 music21 读取配置
    try:
        from music21 import environment
        settings = environment.UserSettings()
        m21_path = settings.get('lilypondPath', None)
        if m21_path:
            p = Path(m21_path)
            if p.exists():
                _LILYPOND_PATH = p
                return p
    except Exception:
        pass

    # Fallback: 常见的安装位置 (跨平台)
    import platform
    if platform.system() == "Windows":
        candidates = [
            Path("F:/U Muse/lilypond/lilypond-2.26.0/bin/lilypond.exe"),
            Path("C:/Program Files/LilyPond/usr/bin/lilypond.exe"),
            Path("C:/lilypond/usr/bin/lilypond.exe"),
        ]
    else:
        # macOS (Homebrew / 手动安装) + Linux
        candidates = [
            Path("/opt/homebrew/bin/lilypond"),       # Apple Silicon Mac (Homebrew)
            Path("/usr/local/bin/lilypond"),           # Intel Mac (Homebrew) / Linux
            Path("/usr/bin/lilypond"),                 # Linux (apt)
            Path("/Applications/LilyPond.app/Contents/Resources/bin/lilypond"),  # macOS .app
        ]
    for c in candidates:
        if c.exists():
            _LILYPOND_PATH = c
            return c

    # 最后尝试 PATH 中查找 (subprocess 会搜索 PATH)
    return Path("lilypond")


def set_lilypond_path(path: Path | str) -> None:
    """手动设置 LilyPond 路径 / Manually set LilyPond path."""
    global _LILYPOND_PATH
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"LilyPond 不存在: {p}")
    _LILYPOND_PATH = p

    # 同步更新 music21 配置
    try:
        from music21 import environment
        environment.UserSettings()['lilypondPath'] = str(p)
    except Exception:
        pass


# ===== 模板系统 =====

class PaperSize(Enum):
    """纸张尺寸 / Paper sizes."""
    A4 = "a4"
    A3 = "a3"
    LETTER = "letter"
    TABLOID = "tabloid"


@dataclass
class LilyPondTemplate:
    """LilyPond 乐谱模板 / LilyPond score template.

    控制乐谱输出的所有排版参数。

    Attributes:
        name: 模板名称
        paper_size: 纸张尺寸
        staff_size: 五线谱大小 (mm, 默认 20)
        system_count: 每页行数 (0=自动)
        top_margin: 上边距 (mm)
        bottom_margin: 下边距 (mm)
        left_margin: 左边距 (mm)
        right_margin: 右边距 (mm)
        indent_first: 首行缩进 (mm, 0=不缩进)
        print_page_numbers: 是否打印页码
        font_family: 字体族 (默认 'lilypond')
        tagline: 页脚版权声明 (None=使用 LilyPond 默认)
    """
    name: str = "default"
    paper_size: PaperSize = PaperSize.A4
    staff_size: float = 20.0
    system_count: int = 0  # 0 = auto
    top_margin: float = 10.0
    bottom_margin: float = 10.0
    left_margin: float = 10.0
    right_margin: float = 10.0
    indent_first: float = 0.0
    print_page_numbers: bool = True
    font_family: str = "lilypond"
    tagline: str | None = None

    def to_lilypond_block(self) -> str:
        """生成 LilyPond \\paper { ... } 块 / Generate LilyPond paper block."""
        lines = ['  \\paper {']
        lines.append(f'    #(set-paper-size "{self.paper_size.value}")')
        lines.append(f'    #(set-default-paper-size "{self.paper_size.value}")')

        if self.staff_size != 20.0:
            lines.append(f'    #(layout-set-staff-size {self.staff_size})')

        if self.system_count > 0:
            lines.append(f'    system-count = #{self.system_count}')

        lines.append(f'    top-margin = {self.top_margin}\\mm')
        lines.append(f'    bottom-margin = {self.bottom_margin}\\mm')
        lines.append(f'    left-margin = {self.left_margin}\\mm')
        lines.append(f'    right-margin = {self.right_margin}\\mm')

        if self.indent_first > 0:
            lines.append(f'    indent = {self.indent_first}\\mm')

        if not self.print_page_numbers:
            lines.append('    print-page-number = ##f')

        if self.tagline is not None:
            lines.append(f'    tagline = "{self.tagline}"')

        lines.append('  }')
        return '\n'.join(lines)

    def to_lilypond_header(self, title: str, composer: str = "") -> str:
        """生成 LilyPond \\header { ... } 块."""
        lines = ['  \\header {']
        lines.append(f'    title = "{title}"')
        if composer:
            lines.append(f'    composer = "{composer}"')
        lines.append(f'    tagline = ##f' if self.tagline is None else f'    tagline = "{self.tagline}"')
        lines.append('  }')
        return '\n'.join(lines)


# 预设模板
TEMPLATE_DEFAULT = LilyPondTemplate(name="default")
TEMPLATE_COMPACT = LilyPondTemplate(
    name="compact",
    staff_size=16.0,
    system_count=0,
    top_margin=5.0,
    bottom_margin=5.0,
    indent_first=0.0,
)
TEMPLATE_FULL_SCORE = LilyPondTemplate(
    name="full_score",
    paper_size=PaperSize.A3,
    staff_size=18.0,
    top_margin=15.0,
    bottom_margin=15.0,
    left_margin=15.0,
    right_margin=15.0,
)
TEMPLATE_LEAD_SHEET = LilyPondTemplate(
    name="lead_sheet",
    staff_size=18.5,
    indent_first=0.0,
    system_count=0,
)


# ===== LilyPond 导出器 =====

class LilyPondExporter:
    """LilyPond 导出器 / LilyPond exporter.

    管理 .ly 文件生成和编译，提供模板化输出。

    用法:
        exporter = LilyPondExporter()
        pdf = exporter.export_pdf(score, "output/song", template=TEMPLATE_COMPACT)
    """

    def __init__(self, lilypond_path: Path | str | None = None):
        """初始化导出器.

        Args:
            lilypond_path: LilyPond 可执行文件路径 (可选, 自动检测)
        """
        if lilypond_path:
            set_lilypond_path(lilypond_path)
        self._ly_path = get_lilypond_path()

    @property
    def lilypond_available(self) -> bool:
        """检查 LilyPond 是否可用."""
        try:
            result = subprocess.run(
                [str(self._ly_path), '--version'],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @property
    def version(self) -> str | None:
        """获取 LilyPond 版本."""
        try:
            result = subprocess.run(
                [str(self._ly_path), '--version'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                # "GNU LilyPond 2.26.0"
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass
        return None

    def export_ly(
        self,
        score,
        output_path: Path | str,
        title: str = "Untitled",
        composer: str = "",
        template: LilyPondTemplate = TEMPLATE_DEFAULT,
    ) -> Path:
        """导出 LilyPond .ly 文件 / Export LilyPond .ly file.

        Args:
            score: music21 Score 或 Stream 对象
            output_path: 输出 .ly 文件路径
            title: 标题
            composer: 作曲者
            template: 排版模板

        Returns:
            生成的 .ly 文件路径
        """
        import music21

        output_path = Path(output_path)
        if output_path.suffix != '.ly':
            output_path = output_path.with_suffix('.ly')

        # 设置元数据
        if not isinstance(score, music21.stream.Score):
            s = music21.stream.Score()
            s.insert(0, score)
            score = s

        md = score.metadata or music21.metadata.Metadata()
        md.title = title
        if composer:
            md.composer = composer
        score.metadata = md

        # 使用 music21 生成 LilyPond (不自动加 .ly 后缀)
        m21_output = output_path.with_suffix('')
        score.write('lilypond', fp=str(m21_output))

        # music21 输出的文件没有 .ly 后缀，读取它
        ly_content = m21_output.read_text(encoding='utf-8')

        # 注入自定义 paper/header 设置
        ly_content = self._inject_template(ly_content, title, composer, template)

        output_path.write_text(ly_content, encoding='utf-8')

        # 重命名 music21 输出文件为带 .ly 后缀
        if m21_output != output_path:
            try:
                m21_output.unlink()  # 删除无后缀版本
            except OSError:
                pass

        return output_path

    def compile(
        self,
        ly_path: Path | str,
        output_dir: Path | str | None = None,
        format: str = "pdf",  # 'pdf', 'png', 'svg'
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Path | None:
        """编译 .ly 文件为 PDF/PNG/SVG.

        Args:
            ly_path: .ly 源文件路径
            output_dir: 输出目录 (默认同 .ly 所在目录)
            format: 输出格式
            progress_callback: 进度回调

        Returns:
            输出文件路径, 或 None (编译失败)

        Raises:
            subprocess.CalledProcessError: LilyPond 编译错误
        """
        ly_path = Path(ly_path).resolve()
        output_dir = Path(output_dir).resolve() if output_dir else ly_path.parent.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if not ly_path.exists():
            raise FileNotFoundError(f"LilyPond 源文件不存在: {ly_path}")

        if progress_callback:
            progress_callback(10, f"编译 {ly_path.name} → {format.upper()}...")

        cmd = [
            str(self._ly_path),
            f'--{format}',
            '-o', str(output_dir),
            str(ly_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=120,  # 复杂乐谱可能需要较长时间
            )

            if result.returncode != 0:
                # LilyPond 编译失败 — 收集错误信息
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise RuntimeError(
                    f"LilyPond 编译失败 (退出码 {result.returncode}):\n{error_msg[:500]}"
                )

            if progress_callback:
                progress_callback(90, "编译完成")

            # 找到输出文件
            output_file = output_dir / f"{ly_path.stem}.{format}"
            if output_file.exists():
                return output_file

            # LilyPond 有时会在文件名后加 -1
            alt_file = output_dir / f"{ly_path.stem}-1.{format}"
            if alt_file.exists():
                return alt_file

            return None

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"LilyPond 编译超时 (120s): {ly_path.name}")
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到 LilyPond 可执行文件: {self._ly_path}\n"
                f"请安装 LilyPond: https://lilypond.org/download.html"
            )

    def export_pdf(
        self,
        score,
        output_path: Path | str,
        title: str = "Untitled",
        composer: str = "",
        template: LilyPondTemplate = TEMPLATE_DEFAULT,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Path | None:
        """一站式导出: Score → .ly → PDF / One-stop export to PDF.

        Args:
            score: music21 Score/Stream
            output_path: 输出路径 (不含扩展名)
            title: 标题
            composer: 作曲者
            template: 模板
            progress_callback: 进度回调

        Returns:
            PDF 文件路径, 或 None
        """
        output_path = Path(output_path)

        if progress_callback:
            progress_callback(20, "生成 .ly 源码...")

        # Step 1: 导出 .ly
        ly_path = self.export_ly(
            score,
            output_path.with_suffix('.ly'),
            title=title,
            composer=composer,
            template=template,
        )

        if progress_callback:
            progress_callback(50, "编译 LilyPond → PDF...")

        # Step 2: 编译 PDF
        pdf_path = self.compile(
            ly_path,
            output_dir=output_path.parent,
            format='pdf',
            progress_callback=progress_callback,
        )

        if progress_callback and pdf_path:
            progress_callback(100, f"PDF 完成: {pdf_path.name}")

        return pdf_path

    def _inject_template(
        self,
        ly_content: str,
        title: str,
        composer: str,
        template: LilyPondTemplate,
    ) -> str:
        """向 .ly 内容注入模板配置 / Inject template settings into .ly content."""
        import re

        header_block = template.to_lilypond_header(title, composer)
        paper_block = template.to_lilypond_block()

        # 1. 移除 music21 生成的旧 \\header { ... } 块 (保留其外部内容)
        ly_content = re.sub(
            r'\\header\s*\{[^}]*\}',
            '',
            ly_content,
            flags=re.DOTALL,
        )

        # 2. 移除 music21 生成的旧 \\paper { ... } 块
        ly_content = re.sub(
            r'\\paper\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}',
            '',
            ly_content,
            flags=re.DOTALL,
        )

        # 3. 在 \\score 前插入新的 header 和 paper
        prefix = f'{header_block}\n{paper_block}\n\n'
        ly_content = re.sub(
            r'(\\score\s*\{)',
            lambda m: prefix + m.group(1),
            ly_content,
            count=1,
        )

        return ly_content


# ===== 便捷函数 =====

def export_ly_file(
    score,
    output_path: Path | str,
    title: str = "Untitled",
    composer: str = "",
    template: LilyPondTemplate = TEMPLATE_DEFAULT,
) -> Path:
    """便捷函数: 导出 .ly 文件 / Convenience: export .ly file."""
    exporter = LilyPondExporter()
    return exporter.export_ly(score, output_path, title, composer, template)


def compile_lilypond(
    ly_path: Path | str,
    output_dir: Path | str | None = None,
    format: str = "pdf",
) -> Path | None:
    """便捷函数: 编译 LilyPond 文件 / Convenience: compile LilyPond file."""
    exporter = LilyPondExporter()
    return exporter.compile(ly_path, output_dir, format)


def compile_to_pdf(
    ly_path: Path | str,
    output_dir: Path | str | None = None,
) -> Path | None:
    """便捷函数: 编译为 PDF / Convenience: compile to PDF."""
    return compile_lilypond(ly_path, output_dir, format="pdf")
