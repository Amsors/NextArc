"""/cancel 指令处理器"""

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.cancel")


class CancelHandler(CommandHandler):
    """取消报名指令"""

    @property
    def command(self) -> str:
        return "cancel"

    def get_usage(self) -> str:
        return "/cancel <序号> - 取消指定序号的报名"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        """处理 /cancel 指令"""
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        # 检查参数
        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n请先使用 /info 查看已报名活动及其序号")

        # 解析序号
        try:
            index = int(args[0])
            if index < 1:
                raise ValueError("序号必须大于0")
        except ValueError:
            return Response.text("❌ 无效的序号，请输入正整数\n\n示例：/cancel 1")

        # 获取已报名活动
        from src.feishu_bot.handlers.info import InfoHandler
        info_handler = InfoHandler()
        info_handler._scanner = self._scanner
        info_handler._db_manager = self._db_manager

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("❌ 暂无数据，请先执行 /update")

        enrolled = await info_handler._get_enrolled_activities(latest_db)

        if not enrolled:
            return Response.text("❌ 您目前没有报名任何活动")

        if index > len(enrolled):
            return Response.text(f"❌ 序号超出范围，您当前已报名 {len(enrolled)} 个活动\n请使用 /info 查看正确的序号")

        # 获取目标活动
        activity = enrolled[index - 1]

        # 检查是否有待确认操作
        if session.confirm and not session.confirm.is_expired():
            return Response.text("⚠️ 您有一个待确认的操作，请先回复「确认」或「取消」")

        # 设置确认会话
        session.set_confirm("cancel", activity.id, activity.name)

        # 返回确认提示
        return Response.text(session.confirm.get_confirm_prompt())

    async def execute_cancel(self, session: UserSession) -> Response:
        """执行取消报名操作"""
        if not session.confirm or session.confirm.operation != "cancel":
            return Response.text("❌ 无效的操作")

        activity_id = session.confirm.activity_id
        activity_name = session.confirm.activity_name

        # 清除确认会话
        session.clear_confirm()

        logger.info(f"执行取消报名: {activity_name} ({activity_id})")

        try:
            # 使用认证会话执行取消
            from pyustc.young.second_class import SecondClass

            async with self._auth_manager.create_session_once():
                # 获取活动实例并取消报名
                # SecondClass 使用单例模式，需要提供 data 参数（可为 None）
                sc = SecondClass(activity_id, {})
                result = await sc.cancel_apply()

                logger.info(f"cancel_apply() 返回值: {result}")

                if not result:
                    return Response.text("❌ 取消报名失败")

            # 成功后不立即扫描，让用户手动 /update
            logger.info(f"取消报名成功: {activity_name}")
            return Response.text(
                f"✅ 已成功取消报名「{activity_name}」\n\n"
                f"💡 提示：执行 /update 可更新报名状态"
            )

        except Exception as e:
            logger.error(f"取消报名失败: {e}")
            return Response.error(str(e), context="取消报名")
