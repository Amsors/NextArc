"""指令处理器模块"""

from typing import Callable, Coroutine, Dict

from .alive import AliveHandler
from .base import CommandHandler
from .cancel import CancelHandler
from .check import CheckHandler
from .info import InfoHandler
from .join import JoinHandler
from .search import SearchHandler
from .update import UpdateHandler
from .help import HelpHandler


def get_all_handlers() -> Dict[str, CommandHandler]:
    """获取所有指令处理器的字典"""
    return {
        "update": UpdateHandler(),
        "更新数据库": UpdateHandler(),
        "更新": UpdateHandler(),

        "check": CheckHandler(),
        "差异": CheckHandler(),
        "检查差异": CheckHandler(),

        "info": InfoHandler(),
        "已报名": InfoHandler(),

        "cancel": CancelHandler(),
        "取消报名": CancelHandler(),
        "取消" : CancelHandler(),

        "search": SearchHandler(),
        "搜索": SearchHandler(),
        "查找": SearchHandler(),

        "join": JoinHandler(),
        "报名": JoinHandler(),

        "alive": AliveHandler(),
        "系统状态": AliveHandler(),
        "状态": AliveHandler(),

        "help": HelpHandler(),
        "帮助": HelpHandler(),
        "?": HelpHandler(),
        "？": HelpHandler(),
    }


__all__ = [
    "CommandHandler",
    "get_all_handlers",
    "UpdateHandler",
    "CheckHandler",
    "InfoHandler",
    "CancelHandler",
    "SearchHandler",
    "JoinHandler",
    "AliveHandler",
    "HelpHandler"
]
