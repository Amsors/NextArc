"""指令处理器模块"""

from typing import TYPE_CHECKING, Dict

from .alive import AliveHandler
from .base import CommandHandler
from .cancel import CancelHandler
from .check import CheckHandler
from .help import HelpHandler
from .ignore import IgnoreHandler
from .info import InfoHandler
from .interested import InterestedHandler
from .menu import MenuHandler
from .join import JoinHandler
from .preference import PreferenceHandler
from .search import SearchHandler
from .upgrade import UpgradeHandler
from .valid import ValidHandler

if TYPE_CHECKING:
    from src.app import AppContext


def get_all_handlers(app_context: "AppContext | None" = None) -> Dict[str, CommandHandler]:
    ret = {}

    check_instructions = [
        "update",
        "check",
        "更新数据库",
        "更新",
        "检查",
        "差异",
        "检查差异",
        "对比",
        "对比差异",
        "扫描"
    ]
    for instruction in check_instructions:
        ret[instruction] = CheckHandler(app_context)

    info_instructions = [
        "info",
        "已报名",
        "已经报名",
    ]
    for instruction in info_instructions:
        ret[instruction] = InfoHandler(app_context)

    cancel_instructions = [
        "cancel",
        "取消报名",
        "取消",
    ]
    for instruction in cancel_instructions:
        ret[instruction] = CancelHandler(app_context)

    search_instructions = [
        "search",
        "搜索",
        "查找",
    ]
    for instruction in search_instructions:
        ret[instruction] = SearchHandler(app_context)

    join_instructions = [
        "join",
        "报名",
        "参加",
        "参与"
    ]
    for instruction in join_instructions:
        ret[instruction] = JoinHandler(app_context)

    alive_instructions = [
        "alive",
        "系统状态",
        "状态",
        "系统信息",
        "系统",
    ]
    for instruction in alive_instructions:
        ret[instruction] = AliveHandler(app_context)

    help_instructions = [
        "help",
        "帮助",
        "?",
        "？",
    ]
    for instruction in help_instructions:
        ret[instruction] = HelpHandler(app_context)

    valid_instructions = [
        "valid",
        "可报名",
        "可报名活动",
    ]
    for instruction in valid_instructions:
        ret[instruction] = ValidHandler(app_context)

    ignore_instructions = [
        "ignore",
        "不感兴趣",
        "忽略",
    ]
    for instruction in ignore_instructions:
        ret[instruction] = IgnoreHandler(app_context)

    interested_instructions = [
        "interested",
        "感兴趣",
    ]
    for instruction in interested_instructions:
        ret[instruction] = InterestedHandler(app_context)

    menu_instructions = [
        "菜单",
        "menu",
        "功能",
    ]
    for instruction in menu_instructions:
        ret[instruction] = MenuHandler(app_context)

    upgrade_instructions = [
        "upgrade",
        "升级",
        "更新程序",
    ]
    for instruction in upgrade_instructions:
        ret[instruction] = UpgradeHandler(app_context)

    preference_instructions = [
        "preference",
        "偏好",
    ]
    for instruction in preference_instructions:
        ret[instruction] = PreferenceHandler(app_context)

    return ret


__all__ = [
    "CommandHandler",
    "get_all_handlers",
    "CheckHandler",
    "InfoHandler",
    "CancelHandler",
    "SearchHandler",
    "JoinHandler",
    "AliveHandler",
    "HelpHandler",
    "ValidHandler",
    "IgnoreHandler",
    "InterestedHandler",
    "MenuHandler",
    "UpgradeHandler",
    "PreferenceHandler",
]
