"""/info 指令处理器"""

import aiosqlite
from pyustc.young import SecondClass, Status

from src.core.filter import SecondClassFilter
from src.models import UserSession, secondclass_from_db_row
from src.notifications import Response
from src.utils.formatter import format_enrolled_list
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.info")


class InfoHandler(CommandHandler):
    """查询已报名活动指令"""

    @property
    def command(self) -> str:
        return "info"

    def get_usage(self) -> str:
        return "/info - 显示已报名的所有活动"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        """处理 /info 指令"""
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        logger.info("执行 /info 指令")

        # 获取最新数据库
        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("暂无数据，请先执行 /update")

        try:
            if not args:
                filter = SecondClassFilter().exclude_status([
                    Status.ABNORMAL,
                    # Status.PUBLISHED,
                    # Status.APPLYING,
                    # Status.APPLY_ENDED,
                    Status.HOUR_PUBLIC,
                    Status.HOUR_APPEND_PUBLIC,
                    Status.PUBLIC_ENDED,
                    Status.HOUR_APPLYING,
                    Status.HOUR_APPROVED,
                    Status.HOUR_REJECTED,
                    Status.FINISHED,
                ])
                hint = "仅显示发布、报名中、报名已结束的活动\n获取更多信息，请输入/info all或/info else\n"
            else:
                if args[0] == "全部" or args[0] == "all" or args[0] == "全部活动" or args[0] == "所有":
                    filter = SecondClassFilter().exclude_status([
                        # Status.ABNORMAL,
                        Status.PUBLISHED,
                        Status.APPLYING,
                        Status.APPLY_ENDED,
                        Status.HOUR_PUBLIC,
                        Status.HOUR_APPEND_PUBLIC,
                        Status.PUBLIC_ENDED,
                        Status.HOUR_APPLYING,
                        Status.HOUR_APPROVED,
                        Status.HOUR_REJECTED,
                        # Status.FINISHED,
                    ])
                    hint = "显示除了结项和异常结项的所有活动\n"
                elif args[0] == "其余" or args[0] == "其他" or args[0] == "else":
                    filter = SecondClassFilter().exclude_status([
                        Status.ABNORMAL,
                        Status.PUBLISHED,
                        Status.APPLYING,
                        Status.APPLY_ENDED,
                        # Status.HOUR_PUBLIC,
                        # Status.HOUR_APPEND_PUBLIC,
                        # Status.PUBLIC_ENDED,
                        # Status.HOUR_APPLYING,
                        # Status.HOUR_APPROVED,
                        # Status.HOUR_REJECTED,
                        Status.FINISHED,
                    ])
                    hint = "显示公示/追加公式中、公示结束、学时申请中、学时审核通过、学时驳回的活动\n"
                else:
                    return Response.error("未知状态码，请输入 /info [all/else]")

            activities = await self._get_enrolled_activities(latest_db, filter)

            if not activities:
                return Response.text("已报名活动\n\n您目前没有报名任何活动")

            return Response.text(f"{hint}{format_enrolled_list(activities)}")

        except Exception as e:
            logger.error(f"查询已报名活动失败: {e}")
            return Response.error(str(e), context="查询已报名活动")

    async def _get_enrolled_activities(self, db_path, filter: SecondClassFilter | None = None) -> list[SecondClass]:
        """从数据库获取已报名活动"""
        activities = []

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                    "SELECT * FROM enrolled_secondclass ORDER BY name"
            ) as cursor:
                async for row in cursor:
                    activities.append(secondclass_from_db_row(dict(row)))

        if filter:
            activities = filter(activities)

        return activities
