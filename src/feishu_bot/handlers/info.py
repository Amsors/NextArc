"""/info 指令处理器"""

from pyustc.young import SecondClass, Status

from src.core.filter import SecondClassFilter
from src.core.repositories import ActivityRepository
from src.core.services import ActivityQueryService
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.info")


class InfoHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "info"

    def get_usage(self) -> str:
        return "/info - 显示已报名的所有活动"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        logger.info("执行 /info 指令")

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
                hint = "仅显示发布、报名中、报名已结束的活动\n"
            else:
                if args[0] == "结项" or args[0] == "end" or args[0] == "已经结项" or args[0] == "已结项":
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
                    hint = "显示结项和异常结项的所有活动\n"
                elif args[0] == "即将结项" or args[0] == "未结项" or args[0] == "pending" or args[0] == "尚未结项":
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
                    hint = "显示公示/追加公示中、公示结束、学时申请中、学时审核通过、学时驳回的活动\n"
                elif args[0] == "异常" or args[0] == "abnormal":
                    filter = SecondClassFilter().exclude_status([
                        Status.ABNORMAL,
                        Status.PUBLISHED,
                        Status.APPLYING,
                        Status.APPLY_ENDED,
                        Status.HOUR_PUBLIC,
                        Status.HOUR_APPEND_PUBLIC,
                        Status.PUBLIC_ENDED,
                        Status.HOUR_APPLYING,
                        Status.HOUR_APPROVED,
                        # Status.HOUR_REJECTED,
                        Status.FINISHED,
                    ])
                    hint = "显示学时驳回的活动\n"
                else:
                    return Response.error("未知状态码，请输入 /info [all/else]")

            activities = await self._get_enrolled_activities(latest_db, filter)

            if not activities:
                return Response.text("已报名活动\n\n您目前没有报名任何活动")

            await session.context_manager.set_displayed_activities(
                activities=activities,
                source="info"
            )

            return Response.enrolled_list(
                activities=activities,
                title="已报名活动",
                filters_applied=[hint.strip()] if hint else None
            )

        except Exception as e:
            logger.error(f"查询已报名活动失败: {e}")
            return Response.error(str(e), context="查询已报名活动")

    async def _get_enrolled_activities(self, db_path, filter: SecondClassFilter | None = None) -> list[SecondClass]:
        service = self._activity_query_service or ActivityQueryService(ActivityRepository())
        return await service.list_enrolled_activities(db_path, filter)
