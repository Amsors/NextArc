"""指令处理器模块"""

from typing import Dict

from .alive import AliveHandler
from .base import CommandHandler
from .cancel import CancelHandler
from .check import CheckHandler
from .help import HelpHandler
from .info import InfoHandler
from .join import JoinHandler
from .search import SearchHandler
from .update import UpdateHandler


def get_all_handlers() -> Dict[str, CommandHandler]:
    """获取所有指令处理器的字典"""
    ret = {}
    update_instructions = [
        "update",
        "更新数据库",
        "更新",
    ]
    for instruction in update_instructions:
        ret[instruction] = UpdateHandler()

    check_instructions = [
        "check",
        "差异",
        "检查差异",
        "对比",
        "检查"
    ]
    for instruction in check_instructions:
        ret[instruction] = CheckHandler()

    info_instructions = [
        "info",
        "已报名",
        "已经报名",
    ]
    for instruction in info_instructions:
        ret[instruction] = InfoHandler()

    cancel_instructions = [
        "cancel",
        "取消报名",
        "取消",
    ]
    for instruction in cancel_instructions:
        ret[instruction] = CancelHandler()

    search_instructions = [
        "search",
        "搜索",
        "查找",
    ]
    for instruction in search_instructions:
        ret[instruction] = SearchHandler()

    join_instructions = [
        "join",
        "报名",
        "参加",
        "参与"
    ]
    for instruction in join_instructions:
        ret[instruction] = JoinHandler()

    alive_instructions = [
        "alive",
        "系统状态",
        "状态",
        "系统信息",
        "系统",
    ]
    for instruction in alive_instructions:
        ret[instruction] = AliveHandler()

    help_instructions = [
        "help",
        "帮助",
        "?",
        "？",
    ]
    for instruction in help_instructions:
        ret[instruction] = HelpHandler()

    return ret


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
