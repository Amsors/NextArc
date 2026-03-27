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

    # 获取根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有 handler，避免重复输出
    root_logger.handlers.clear()

    # 创建控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # 设置统一格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # 添加 handler 到根 logger
    root_logger.addHandler(console_handler)

    # 如果启用文件日志，添加 FileHandler
    if file_enabled and file_path:
        try:
            # 确保日志目录存在
            log_dir = file_path.parent
            log_dir.mkdir(parents=True, exist_ok=True)

            # 创建 RotatingFileHandler
            file_handler = RotatingFileHandler(
                filename=file_path,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding="utf-8",
                delay=True,  # 延迟创建文件直到第一次写入
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)

            # 添加 handler 到根 logger
            root_logger.addHandler(file_handler)

            # 记录文件日志已启用（使用 stderr 避免循环）
            print(f"文件日志已启用: {file_path}", file=sys.stderr)

        except Exception as e:
            # 文件日志初始化失败，记录警告但不影响控制台日志
            print(f"警告: 文件日志初始化失败: {e}", file=sys.stderr)

    # 设置第三方库的日志级别（降低噪音）
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    # HTTP 相关库
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # WebSocket 相关库
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    # 数据库相关库
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    # 时间相关库
    logging.getLogger("tzlocal").setLevel(logging.WARNING)
    # OpenAI 相关库
    logging.getLogger("openai").setLevel(logging.WARNING)
    # Lark SDK 日志级别保持 INFO，以便看到连接状态
    logging.getLogger("Lark").setLevel(logging.INFO)

    return logging.getLogger("nextarc")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 logger 实例"""
    if name:
        return logging.getLogger(f"nextarc.{name}")
    return logging.getLogger("nextarc")
