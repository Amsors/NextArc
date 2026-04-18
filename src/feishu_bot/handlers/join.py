"""/join 指令处理器"""

from pyustc.young import Status

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from src.feishu_bot.calendar_service import CalendarService
from .base import CommandHandler

logger = get_logger("feishu.handler.join")


def _should_sync_calendar(session: UserSession, sc) -> tuple[bool, str]:
    """
    判断是否应该同步日历。
    
    Returns:
        (should_sync, reason): 是否同步，以及原因描述
    """
    # 1. 检查配置是否启用
    from src.config import get_settings
    settings = get_settings()
    if not settings.feishu.calendar_sync.enabled:
        return False, ""
    
    # 2. 检查活动是否有有效时间
    if not sc.hold_time or not sc.hold_time.start:
        logger.info(f"活动 {sc.name} 无有效时间信息，跳过日历同步")
        return False, ""
    
    # 3. 检查用户 open_id
    if not session.open_id or not JoinHandler._bot:
        return False, ""
    
    # 4. OAuth 模式：检查用户是否已绑定
    if settings.feishu.calendar_sync.mode == "oauth":
        if not session.feishu_user_token:
            logger.info(f"OAuth 模式但用户未绑定日历，跳过同步")
            return False, ""
    
    return True, ""


class JoinHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "join"

    def get_usage(self) -> str:
        return "/join <序号> - 报名搜索结果的指定活动"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        if not session.search or session.search.is_expired():
            return Response.text("请先使用 /search 搜索活动\n\n示例：/search 讲座")

        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n当前搜索结果可用序号：1-{len(session.search.results)}")

        try:
            index = int(args[0])
            if index < 1:
                raise ValueError("序号必须大于0")
        except ValueError:
            return Response.text("无效的序号，请输入正整数\n\n示例：/join 1")

        activity = session.search.get_result_by_index(index)

        if not activity:
            return Response.text(f"序号超出范围，当前搜索结果共 {len(session.search.results)} 个活动")

        if activity.applied:
            return Response.text(f"您已经报名了「{activity.name}」")

        if activity.status != Status.APPLYING and activity.status != Status.PUBLISHED:
            return Response.text(f"「{activity.name}」当前状态不可报名\n状态：{activity.status()}")

        if session.confirm and not session.confirm.is_expired():
            return Response.text("您有一个待确认的操作，请先回复「确认」或「取消」")

        session.set_confirm("join", activity.id, activity.name)

        return Response.text(session.confirm.get_confirm_prompt())

    async def execute_join(self, session: UserSession) -> Response:
        if not session.confirm or session.confirm.operation != "join":
            return Response.text("无效的操作")

        activity_id = session.confirm.activity_id
        activity_name = session.confirm.activity_name

        session.clear_confirm()
        session.clear_search()

        logger.info(f"执行报名: {activity_name} ({activity_id})")

        try:
            from pyustc.young.second_class import SecondClass

            async with self._auth_manager.create_session_once():
                sc = SecondClass(activity_id, {})

                await sc.update()

                if not sc.applyable:
                    return Response.text(
                        f"「{activity_name}」当前不可报名\n状态：{sc.status.text if sc.status else '未知'}")

                if sc.need_sign_info:
                    from pyustc.young.second_class import SignInfo
                    sign_info = await SignInfo.get_self()
                    result = await sc.apply(force=True, auto_cancel=False, sign_info=sign_info)
                else:
                    result = await sc.apply(force=True, auto_cancel=False)
                    # TODO 添加是否强制报名的配置

                logger.info(f"apply() 返回值: {result}")

                if not result:
                    return Response.text(f"报名失败：活动不可报名或名额已满")

            logger.info(f"报名成功: {activity_name}")

            # 同步到飞书日历
            calendar_msg = ""
            should_sync, _ = _should_sync_calendar(session, sc)
            if should_sync:
                try:
                    cal_svc = CalendarService(JoinHandler._bot.app_id, JoinHandler._bot.app_secret)
                    user_token = session.feishu_user_token
                    cal_result = await cal_svc.create_event_from_secondclass(session.open_id, sc, user_token)
                    if cal_result.get("code") == 0:
                        calendar_msg = "\n📅 日程已同步到你的飞书日历"
                        logger.info(f"日历同步成功: {activity_name}")
                    else:
                        logger.warning(f"日历同步失败: code={cal_result.get('code')} msg={cal_result.get('msg')}")
                except Exception as cal_e:
                    logger.error(f"日历同步异常: {cal_e}")

            return Response.text(
                f"已成功报名「{activity_name}」{calendar_msg}\n\n"
                # TODO 自动更新已报名活动
            )

        except Exception as e:
            logger.error(f"报名失败: {e}")
            return Response.error(str(e), context="报名")
