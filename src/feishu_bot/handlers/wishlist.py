"""/wishlist 指令处理器 - 查看感兴趣/不感兴趣列表"""

import aiosqlite

from src.core import DatabaseManager, UserPreferenceManager
from src.models import UserSession, secondclass_from_db_row
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.wishlist")


class WishlistHandler(CommandHandler):
    _db_manager: DatabaseManager = None
    _user_preference_manager: UserPreferenceManager = None

    @classmethod
    def set_dependencies(
            cls,
            db_manager: DatabaseManager,
            user_preference_manager: UserPreferenceManager
    ) -> None:
        cls._db_manager = db_manager
        cls._user_preference_manager = user_preference_manager

    @property
    def command(self) -> str:
        return "wishlist"

    def get_usage(self) -> str:
        return "/wishlist [感兴趣|不感兴趣] - 查看已标记的活动列表"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self._user_preference_manager:
            return Response.text("功能未初始化，请稍后重试")

        if not args:
            # 无参数：分别显示两个列表
            interested_text = await self._build_list("interested")
            ignored_text = await self._build_list("ignored")

            if not interested_text and not ignored_text:
                return Response.text(
                    "你还没有标记任何感兴趣或不感兴趣的活动\n\n"
                    "在活动卡片中点击按钮即可标记"
                )

            parts = []
            if interested_text:
                parts.append(f"⭐ **感兴趣**\n{interested_text}\n")
            if ignored_text:
                parts.append(f"🚫 **不感兴趣**\n{ignored_text}\n")

            parts.append("💡 提示：在活动卡片中点击按钮可重新标记状态")

            return Response.text("\n".join(parts))

        # 有参数：只看指定列表
        arg = args[0].lower()
        if arg in ("感兴趣", "interested", "i"):
            status = "interested"
            label = "感兴趣"
        elif arg in ("不感兴趣", "ignored", "ignore", "n"):
            status = "ignored"
            label = "不感兴趣"
        else:
            return Response.text(
                f"未知类型: {args[0]}\n\n"
                "用法：\n"
                "• /wishlist - 查看全部\n"
                "• /wishlist 感兴趣 - 只看感兴趣\n"
                "• /wishlist 不感兴趣 - 只看不感兴趣"
            )

        text = await self._build_list(status)
        if not text:
            empty_text = {
                "interested": "你还没有标记任何感兴趣的活动\n\n在活动卡片中点击「感兴趣」按钮即可标记",
                "ignored": "你还没有标记任何不感兴趣的活动",
            }
            return Response.text(empty_text[status])

        prefix = {
            "interested": "⭐ **感兴趣**\n",
            "ignored": "🚫 **不感兴趣**\n",
        }
        return Response.text(prefix[status] + text)

    async def _build_list(self, status: str) -> str:
        """构建指定状态的列表文本"""
        if not self._user_preference_manager:
            return ""

        # 使用实际存在的方法
        if status == "interested":
            activity_ids = await self._user_preference_manager.get_all_interested_ids()
        elif status == "ignored":
            activity_ids = await self._user_preference_manager.get_all_ignored_ids()
        else:
            return ""

        if not activity_ids:
            return ""

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return "(数据库为空)"

        placeholders = ",".join(["?"] * len(activity_ids))
        query = f"SELECT * FROM all_secondclass WHERE id IN ({placeholders})"

        activities = []
        try:
            async with aiosqlite.connect(latest_db) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(query, tuple(activity_ids)) as cursor:
                    async for row in cursor:
                        activities.append(secondclass_from_db_row(dict(row)))
        except Exception as e:
            logger.error(f"查询 {status} 列表失败: {e}")
            return f"(查询失败: {e})"

        if not activities:
            return "(活动已不存在)"

        lines = []
        for i, act in enumerate(activities, 1):
            name = act.name[:30]
            status_tag = ""
            if status == "interested":
                # 顺便看看活动状态
                from pyustc.young import Status
                if act.status == Status.APPLYING.code:
                    status_tag = " 🎯 可报名"
                elif act.status == Status.PUBLISHED.code:
                    status_tag = " 📢 已发布"
            lines.append(f"  {i}. {name}{status_tag}")

        return "\n".join(lines)
