"""日志配置模块"""

import logging
import sys
from typing import Optional


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """
    配置日志输出到命令行
    
    Args:
        level: 日志级别，默认为 INFO
        
    Returns:
        配置好的 logger 实例
    """
    if level is None:
        level = "INFO"

    # 创建 logger
    logger = logging.getLogger("nextarc")
    logger.setLevel(getattr(logging, level.upper()))

    # 清除已有 handler
    logger.handlers.clear()

    # 创建控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    # 设置格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # 添加 handler
    logger.addHandler(console_handler)

    # 设置第三方库的日志级别
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 logger 实例"""
    if name:
        return logging.getLogger(f"nextarc.{name}")
    return logging.getLogger("nextarc")
