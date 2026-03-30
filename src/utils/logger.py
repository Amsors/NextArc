"""日志配置模块"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(
        level: Optional[str] = None,
        file_enabled: bool = False,
        file_path: Optional[Path] = None,
        max_size_mb: int = 10,
        backup_count: int = 5,
) -> logging.Logger:
    """
    配置根日志输出到命令行和文件（可选），统一整个项目的日志格式

    Args:
        level: 日志级别，默认为 INFO
        file_enabled: 是否启用文件日志
        file_path: 日志文件路径
        max_size_mb: 单个日志文件最大大小（MB）
        backup_count: 保留的历史日志文件数量

    Returns:
        配置好的 logger 实例
    """
    if level is None:
        level = "INFO"

    log_level = getattr(logging, level.upper())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if file_enabled and file_path:
        try:
            log_dir = file_path.parent
            log_dir.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                filename=file_path,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

            print(f"文件日志已启用: {file_path}", file=sys.stderr)

        except Exception as e:
            print(f"警告: 文件日志初始化失败: {e}", file=sys.stderr)

    # 降低第三方库日志级别
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("tzlocal").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    lark_logger = logging.getLogger("Lark")
    lark_logger.setLevel(logging.INFO)
    lark_logger.handlers.clear()
    lark_logger.propagate = True

    return logging.getLogger("nextarc")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 logger 实例"""
    if name:
        return logging.getLogger(f"nextarc.{name}")
    return logging.getLogger("nextarc")
