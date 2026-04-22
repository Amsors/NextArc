"""/cancel 指令处理器"""

from pyustc.young import Status

from src.core.repositories import ActivityRepository
from src.core.services import ActivityQueryService
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler
from ...core import SecondClassFilter

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

        filter = SecondClassFilter().exclude_status([
            Status.ABNORMAL,
            Status.HOUR_PUBLIC,
            Status.HOUR_APPEND_PUBLIC,
            Status.PUBLIC_ENDED,
            Status.HOUR_APPLYING,
            Status.HOUR_APPROVED,
            Status.HOUR_REJECTED,
            Status.FINISHED,
        ])

        query_service = self._activity_query_service or ActivityQueryService(ActivityRepository())
        enrolled = await query_service.list_enrolled_activities(latest_db, filter)

        if not enrolled:
            return Response.text("您目前没有报名任何活动")

        if index > len(enrolled):
            return Response.text(f"序号超出范围，您当前已报名 {len(enrolled)} 个活动\n请使用 /info 查看正确的序号")

        activity = enrolled[index - 1]

        if session.confirm and not session.confirm.is_expired():
            return Response.text("您有一个待确认的操作，请先回复「确认」或「取消」")

        session.set_confirm("cancel", activity.id, activity.name)

        return Response.text(session.confirm.get_confirm_prompt())

    async def execute_cancel(self, session: UserSession) -> Response:
        if not session.confirm or session.confirm.operation != "cancel":
            return Response.text("无效的操作")

        activity_id = session.confirm.activity_id
        activity_name = session.confirm.activity_name

        session.clear_confirm()

        logger.info(f"执行取消报名: {activity_name} ({activity_id})")

        try:
            enrollment_service = self._enrollment_service
            if enrollment_service is None:
                from src.core.services import EnrollmentService
                enrollment_service = EnrollmentService(self._auth_manager)

            result = await enrollment_service.cancel_activity(activity_id, activity_name)
            if result.success:
                return Response.text(f"{result.message}\n")
            return Response.text(result.message)

        except Exception as e:
            logger.error(f"取消报名失败: {e}")
            return Response.error(str(e), context="取消报名")
