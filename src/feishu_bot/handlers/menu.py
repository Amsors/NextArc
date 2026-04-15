"""/菜单 指令处理器 - 发送交互式菜单卡片"""

from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.menu")


def build_menu_card() -> dict:
    """构建菜单卡片"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📋 NextArc 功能菜单"},
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "👋 点击下方按钮执行对应功能"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**📋 已报名**\n查看你已报名的活动"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📋 已报名"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "info"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📋 已报名(全部)"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "info", "args": ["全部"]}
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**🔍 可报名活动**\n查看当前可以报名的活动"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔍 可报名"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "valid"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔍 可报名(全部)"},
                        "type": "primary",
                        "value": {"action": "menu_cmd", "cmd": "valid", "args": ["全部"]}
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**🔎 搜索活动**\n输入 /搜索 关键词 来搜索"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**🔄 扫描更新**\n手动触发一次数据库扫描"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔄 立即扫描"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "update"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📊 检查差异"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "check"}
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**ℹ️ 系统状态**\n查看服务运行状态"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "ℹ️ 系统状态"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "alive"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❓ 帮助"},
                        "type": "default",
                        "value": {"action": "menu_cmd", "cmd": "help"}
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**💡 提示**\n- 搜索结果有效期 5 分钟\n- 报名/取消需要二次确认\n- 热门活动名额有限，看到请抓紧报名 🎯"
                }
            }
        ]
    }


class MenuHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "菜单"

    def get_usage(self) -> str:
        return "/菜单 - 显示功能菜单"

    async def handle(self, args: list[str], session) -> Response:
        if not self._bot:
            return Response.text("服务未初始化，请稍后重试")

        logger.info("执行 /菜单 指令")

        card = build_menu_card()
        await self._bot.send_card(card)

        # 返回 None，不通过通知服务再发一次
        return Response.none()
