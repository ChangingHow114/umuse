"""Demucs 分轨引擎 / Demucs Stem Separator.

通过子进程调用 demucs CLI，解析输出进度。
封装为可复用的 StemSeparator 类。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from src.config.constants import DEMUCS_6S_STEMS, DEMUCS_4S_STEMS


class StemSeparator:
    """Demucs 音频分轨器 / Demucs-based stem separator.

    用法:
        sep = StemSeparator()
        stems = sep.separate("song.mp3", "output/", model="htdemucs_6s")
        # stems = {"drums": Path("..."), "bass": Path("..."), ...}
    """

    # 可用模型
    AVAILABLE_MODELS: tuple[str, ...] = (
        "htdemucs_6s",   # 6 轨 (推荐)
        "htdemucs",      # 4 轨
        "htdemucs_ft",   # 4 轨 (微调)
        "hdemucs_mmi",   # 4 轨 (混合)
    )

    # 进度匹配正则 (Demucs 输出格式)
    _PROGRESS_RE = re.compile(r"(\d+)/(\d+)")
    _SEPARATED_RE = re.compile(r"Separated (.*)")

    def __init__(self, device: str = "auto"):
        """初始化分轨器.

        Args:
            device: 设备选择 ('auto' | 'cuda' | 'cpu')
        """
        self.device = device
        self._demucs_cmd = self._find_demucs()

    @staticmethod
    def _find_demucs() -> str:
        """查找 demucs 命令路径."""
        # 优先使用 python -m demucs.separate
        cmd = shutil.which("demucs")
        if cmd:
            return "demucs"
        # Fallback: 使用 python -m
        return "python -m demucs.separate"

    def separate(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        model: str = "htdemucs_6s",
        shifts: int = 1,
        overlap: float = 0.25,
        mp3: bool = False,
        mp3_bitrate: int = 320,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Path]:
        """执行音频分轨 / Run stem separation.

        Args:
            input_path: 输入音频文件路径
            output_dir: 输出根目录
            model: 模型名称 (htdemucs_6s / htdemucs / htdemucs_ft / hdemucs_mmi)
            shifts: SHIFT 增强次数 (0=最快, 越大越精确但越慢)
            overlap: 重叠度 (0-1, 推荐 0.25)
            mp3: 是否输出 MP3 格式 (默认 WAV)
            mp3_bitrate: MP3 比特率 (kbps)
            progress_callback: 进度回调 (percent, message)

        Returns:
            {英文乐器名: stem 文件路径}

        Raises:
            FileNotFoundError: 输入文件不存在
            RuntimeError: Demucs 执行失败
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if model not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"不支持的模型: {model}, 可用: {self.AVAILABLE_MODELS}"
            )

        # 构建命令
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "python", "-m", "demucs.separate",
            "-n", model,
            "-o", str(output_dir),
            "-d", self.device,
            "--shifts", str(shifts),
            "--overlap", str(overlap),
        ]
        if mp3:
            cmd.extend(["--mp3", "--mp3-bitrate", str(mp3_bitrate)])
        cmd.append(str(input_path))

        if progress_callback:
            progress_callback(0, f"开始分轨 (模型: {model})...")

        # 执行 Demucs
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            output_lines: list[str] = []
            for line in process.stdout:
                line = line.strip()
                if line:
                    output_lines.append(line)
                    # 尝试解析进度
                    match = self._PROGRESS_RE.search(line)
                    if match and progress_callback:
                        current, total = int(match.group(1)), int(match.group(2))
                        pct = int(current / total * 90)  # 留 10% 给后处理
                        progress_callback(pct, f"分轨中... ({current}/{total})")

            process.wait(timeout=3600)  # 最长等待 1 小时

            if process.returncode != 0:
                error_msg = "\n".join(output_lines[-10:])  # 最后 10 行
                raise RuntimeError(f"Demucs 执行失败 (返回码: {process.returncode}):\n{error_msg}")

        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError("Demucs 执行超时 (> 1小时)，音频可能过长或模型未下载完成")

        if progress_callback:
            progress_callback(90, "收集分轨结果...")

        # 定位输出文件
        # Demucs 输出结构: output_dir/model_name/audio_name/stem_name.wav
        model_output_dir = output_dir / model
        audio_name = input_path.stem

        stems = self._locate_stems(model_output_dir / audio_name, model)

        if not stems:
            # 尝试直接在 model_output_dir 下查找
            stems = self._locate_stems(model_output_dir, model)
        if not stems:
            raise RuntimeError(
                f"未找到分轨输出文件。"
                f"请检查 {model_output_dir} 目录"
            )

        if progress_callback:
            progress_callback(100, f"分轨完成! {len(stems)} 轨已分离")

        return stems

    def _locate_stems(self, directory: Path, model: str) -> dict[str, Path]:
        """在目录中查找 stem 文件.

        Args:
            directory: Demucs 输出目录
            model: 模型名称

        Returns:
            {stem_name: file_path}
        """
        if not directory.exists():
            return {}

        stems = {}
        extensions = (".wav", ".flac", ".mp3")

        # 根据模型确定期望的 stem 名称
        if "6s" in model:
            expected_stems = list(DEMUCS_6S_STEMS.keys())
        else:
            expected_stems = list(DEMUCS_4S_STEMS.keys())

        for stem_name in expected_stems:
            for ext in extensions:
                candidate = directory / f"{stem_name}{ext}"
                if candidate.exists():
                    stems[stem_name] = candidate
                    break

        # 如果没找全，尝试暴力搜索
        if len(stems) < len(expected_stems):
            for f in directory.iterdir():
                if f.suffix.lower() in extensions:
                    stem_name = f.stem.lower()
                    if stem_name not in stems:
                        # 检查是否为已知 stem 名
                        if stem_name in expected_stems:
                            stems[stem_name] = f

        return stems

    def get_available_models(self) -> tuple[str, ...]:
        """获取可用模型列表."""
        return self.AVAILABLE_MODELS

    @staticmethod
    def get_stem_info(model: str) -> dict[str, str]:
        """获取模型对应的分轨乐器信息.

        Returns:
            {英文名: 中文名}
        """
        if "6s" in model:
            return dict(DEMUCS_6S_STEMS)
        return dict(DEMUCS_4S_STEMS)
