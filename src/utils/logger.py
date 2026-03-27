"""日志配置模块"""

import logging
import sys
from typing import Optional


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """
    配置根日志输出到命令行，统一整个项目的日志格式
    
    Args:
        level: 日志级别，默认为 INFO
        
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
    # Lark SDK 日志级别保持 INFO，以便看到连接状态
    logging.getLogger("Lark").setLevel(logging.INFO)

    return logging.getLogger("nextarc")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 logger 实例"""
    if name:
        return logging.getLogger(f"nextarc.{name}")
    return logging.getLogger("nextarc")
