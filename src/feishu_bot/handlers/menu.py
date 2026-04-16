"""/菜单 指令处理器"""

from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.menu")


def build_menu_card() -> dict:
    """构建功能菜单卡片。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "NextArc 功能菜单"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "点击下方按钮执行现有指令。",
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**已报名**\n查看你已报名的活动",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "已报名"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "info"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "已报名(全部)"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "info", "args": ["全部"]},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**可报名活动**\n查看当前可以报名的活动",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "可报名"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "valid"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "可报名(全部)"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "valid", "args": ["全部"]},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**扫描更新**\n手动触发一次数据库扫描",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "扫描"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "check"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "扫描并推送"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "check", "args": ["推送"]},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**系统状态**\n查看服务运行状态",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "系统状态"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "alive"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "帮助"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "help"},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**搜索**\n搜索请直接发送 `/search 关键词` 或 `搜索 关键词`。",
                },
            },
        ],
    }


class MenuHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "菜单"

    def get_usage(self) -> str:
        return "/菜单 - 显示功能菜单"

    async def handle(self, args: list[str], session) -> Response:
        logger.info("执行 /菜单 指令")
        return Response.card(build_menu_card())
