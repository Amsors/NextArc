"""/join 指令处理器"""

from pyustc.young import Status

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.join")


class JoinHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "join"

    def get_usage(self) -> str:
        return "/join <序号> - 报名搜索结果的指定活动"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        search_result = await session.context_manager.get_search_result()
        if not search_result:
            return Response.text("请先使用 /search 搜索活动\n\n示例：/search 讲座")

        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n当前搜索结果可用序号：1-{len(search_result.results)}")

        try:
            index = int(args[0])
            if index < 1:
                raise ValueError("序号必须大于0")
        except ValueError:
            return Response.text("无效的序号，请输入正整数\n\n示例：/join 1")

        activity = search_result.get_result_by_index(index)

        if not activity:
            return Response.text(f"序号超出范围，当前搜索结果共 {len(search_result.results)} 个活动")

        if activity.applied:
            return Response.text(f"您已经报名了「{activity.name}」")

        if activity.status != Status.APPLYING and activity.status != Status.PUBLISHED:
            status_text = activity.status.text if activity.status else "未知"
            return Response.text(f"「{activity.name}」当前状态不可报名\n状态：{status_text}")

        if await session.context_manager.get_confirmation():
            return Response.text("您有一个待确认的操作，请先回复「确认」或「取消」")

        await session.context_manager.set_confirmation("join", activity.id, activity.name)
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation:
            return Response.text("创建确认操作失败，请稍后重试")

        return Response.text(confirmation.get_confirm_prompt())

    async def execute_join(self, session: UserSession) -> Response:
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation or confirmation.operation != "join":
            return Response.text("无效的操作")

        activity_id = confirmation.activity_id
        activity_name = confirmation.activity_name

        await session.context_manager.clear_confirmation()
        await session.clear_search()

        logger.info(f"执行报名: {activity_name} ({activity_id})")

        try:
            enrollment_service = self._enrollment_service
            if enrollment_service is None:
                return Response.text("报名服务未初始化，请稍后重试")

            result = await enrollment_service.join_activity(
                activity_id,
                activity_name,
                user_id=session.user_id,
                force=True,
                auto_cancel=False,
                precheck_applyable=True,
            )

            if result.success:
                return Response.text(f"{result.message}\n\n")
            return Response.text(result.message)

        except Exception as e:
            logger.error(f"报名失败: {e}")
            return Response.error(str(e), context="报名")
