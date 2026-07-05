# 配置层 / Configuration Layer

import logging
import sys
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | str | None = None,
    console_level: int = logging.WARNING,
) -> logging.Logger:
    """初始化全局日志配置 / Initialize global logging configuration.

    配置两个 handler:
    - 控制台 handler: 输出 WARNING 及以上级别到 stderr
    - 文件 handler: 输出 INFO 及以上级别到指定的日志文件

    用法 (在 main.py 或 app.py 开头调用):
        from src.config import setup_logging
        setup_logging(log_file="logs/umuse.log")

    Args:
        level: 文件 handler 的最低日志级别 (默认 INFO)
        log_file: 日志文件路径 (None = 不写文件)
        console_level: 控制台 handler 的最低日志级别 (默认 WARNING)

    Returns:
        Root logger
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # 让所有消息到达 handler, handler 各自过滤

    # 清除已有的 handler (避免重复)
    root.handlers.clear()

    # 统一格式
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台 handler (stderr)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 文件 handler (可选)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # 抑制第三方库的 DEBUG 日志
    for noisy in ("matplotlib", "PIL", "urllib3", "librosa", "music21"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info("日志系统已初始化 (console=%s, file=%s)",
              logging.getLevelName(console_level),
              str(log_file) if log_file else "无")

    return root
