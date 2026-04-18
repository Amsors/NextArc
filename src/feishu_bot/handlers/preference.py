"""/preference 指令处理器 - 查看感兴趣/不感兴趣列表"""

from pyustc.young import Status

from src.core import DatabaseManager, UserPreferenceManager
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.preference")


class PreferenceHandler(CommandHandler):
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
        return "preference"

    def get_usage(self) -> str:
        return "/preference [感兴趣|不感兴趣] - 查看已标记的活动列表"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self._user_preference_manager or not self._db_manager:
            return Response.text("功能未初始化，请稍后重试")

        if not args:
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

        arg = args[0].lower()
        if arg in ("感兴趣", "interested", "i"):
            preference_type = "interested"
        elif arg in ("不感兴趣", "ignored", "ignore", "n"):
            preference_type = "ignored"
        else:
            return Response.text(
                f"未知类型: {args[0]}\n\n"
                "用法：\n"
                "• /preference - 查看全部\n"
                "• /preference 感兴趣 - 只看感兴趣\n"
                "• /preference 不感兴趣 - 只看不感兴趣"
            )

        text = await self._build_list(preference_type)
        if not text:
            empty_text = {
                "interested": "你还没有标记任何感兴趣的活动\n\n在活动卡片中点击「感兴趣」按钮即可标记",
                "ignored": "你还没有标记任何不感兴趣的活动",
            }
            return Response.text(empty_text[preference_type])

        prefix = {
            "interested": "⭐ **感兴趣**\n",
            "ignored": "🚫 **不感兴趣**\n",
        }
        return Response.text(prefix[preference_type] + text)

    async def _build_list(self, preference_type: str) -> str:
        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return "(数据库为空)"

        activities = await self._user_preference_manager.get_preference_activities(latest_db, preference_type)
        if not activities:
            return ""

        lines = []
        for i, act in enumerate(activities, 1):
            name = act.name[:30]
            suffix = ""
            if preference_type == "interested":
                if act.status == Status.APPLYING:
                    suffix = " 🎯 可报名"
                elif act.status == Status.PUBLISHED:
                    suffix = " 📢 已发布"
            lines.append(f"  {i}. {name}{suffix}")

        return "\n".join(lines)
