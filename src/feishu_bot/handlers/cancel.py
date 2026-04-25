"""/cancel 指令处理器"""

from pyustc.young import Status

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.cancel")


class CancelHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "cancel"

    def get_usage(self) -> str:
        return "/cancel <序号> - 取消指定序号的报名"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n请先使用 /info 查看已报名活动及其序号")

        try:
            index = int(args[0])
            if index < 1:
                raise ValueError("序号必须大于0")
        except ValueError:
            return Response.text("无效的序号，请输入正整数\n\n示例：/cancel 1")

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("暂无数据，请先执行 /update")

        excluded_statuses = [
            Status.ABNORMAL,
            Status.HOUR_PUBLIC,
            Status.HOUR_APPEND_PUBLIC,
            Status.PUBLIC_ENDED,
            Status.HOUR_APPLYING,
            Status.HOUR_APPROVED,
            Status.HOUR_REJECTED,
            Status.FINISHED,
        ]

        if not self._activity_query_service:
            return Response.text("活动查询服务未初始化，请稍后重试")

        enrolled = await self._activity_query_service.list_enrolled_activities(
            latest_db,
            excluded_statuses=excluded_statuses,
        )

        if not enrolled:
            return Response.text("您目前没有报名任何活动")

        if index > len(enrolled):
            return Response.text(f"序号超出范围，您当前已报名 {len(enrolled)} 个活动\n请使用 /info 查看正确的序号")

        activity = enrolled[index - 1]

        if await session.context_manager.get_confirmation():
            return Response.text("您有一个待确认的操作，请先回复「确认」或「取消」")

        await session.context_manager.set_confirmation("cancel", activity.id, activity.name)
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation:
            return Response.text("创建确认操作失败，请稍后重试")

        return Response.text(confirmation.get_confirm_prompt())

    async def execute_cancel(self, session: UserSession) -> Response:
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation or confirmation.operation != "cancel":
            return Response.text("无效的操作")

        activity_id = confirmation.activity_id
        activity_name = confirmation.activity_name

        await session.context_manager.clear_confirmation()

        logger.info(f"执行取消报名: {activity_name} ({activity_id})")

        try:
            enrollment_service = self._enrollment_service
            if enrollment_service is None:
                return Response.text("报名服务未初始化，请稍后重试")

            result = await enrollment_service.cancel_activity(activity_id, activity_name)
            if result.success:
                return Response.text(f"{result.message}\n")
            return Response.text(result.message)

        except Exception as e:
            logger.error(f"取消报名失败: {e}")
            return Response.error(str(e), context="取消报名")
