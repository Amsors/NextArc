"""不感兴趣指令处理器"""

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.ignore")


class IgnoreHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "ignore"

    def get_usage(self) -> str:
        return (
            "/ignore <序号> 或 不感兴趣 <序号> - 将活动加入忽略列表\n"
            "  序号格式: 1,2,3 或 1-5 或 全部"
        )

    async def handle(self, args: list[str], session: UserSession) -> Response:
        context_manager = session.context_manager
        preference_manager = self._user_preference_manager
        if not preference_manager:
            return Response.text("忽略功能未初始化")

        if not args:
            return Response.text(
                "格式错误\n\n"
                "用法：\n"
                "• /ignore 1,2,3 - 忽略第1、2、3个活动\n"
                "• /ignore 1-5 - 忽略第1到5个活动\n"
                "• /ignore 1,3-5,10 - 组合使用\n"
                "• /ignore 全部 - 忽略所有显示的活动\n"
                "\n也可用「不感兴趣」代替「/ignore」"
            )

        if args[0] == "AI" or args[0] == "ai":
            ai_filtered_activities = await context_manager.get_filtered_activities_by_type("ai")

            if not ai_filtered_activities:
                return Response.text("没有AI忽略的活动")

            ai_filtered_activities_ids = [activity.activity_id for activity in ai_filtered_activities]

            success_count, failed_count = await preference_manager.add_ignored_activities(ai_filtered_activities_ids)

            if failed_count != 0:
                return Response.text(f"添加失败，{failed_count}个活动未添加, {success_count}个活动成功添加")

            return Response.text(f"已添加AI筛选出的{success_count}个活动到不感兴趣列表")

        indices_str = " ".join(args).strip()

        displayed_activities = await context_manager.get_all_displayed_activities()

        if not displayed_activities:
            return Response.text(
                "没有可操作的最近活动列表\n\n"
                "请先用以下指令查看活动：\n"
                "• /valid - 查看可报名活动\n"
                "• /search <关键词> - 搜索活动"
            )

        indices, errors = await context_manager.parse_displayed_indices(indices_str)

        if errors:
            error_msg = "\n".join(f"  • {e}" for e in errors)
            return Response.text(f"解析失败\n\n{error_msg}")

        if not indices:
            return Response.text(
                "没有有效的活动序号\n\n"
                f"有效范围：1-{len(displayed_activities)}"
            )

        activity_ids = []
        activity_names = []

        for idx in indices:
            activity = await context_manager.get_displayed_activity_by_index(idx)
            if activity:
                activity_ids.append(activity.id)
                activity_names.append(f"[{idx}] {activity.name}")

        if not activity_ids:
            return Response.text("无法获取活动信息，请重试")

        success_count, failed_count = await preference_manager.add_ignored_activities(activity_ids)

        if success_count == 0:
            return Response.text("添加失败，请稍后重试")

        lines = ["已添加到不感兴趣列表\n"]

        lines.append(f"成功添加 {success_count} 个活动：")
        for name in activity_names[:10]:
            lines.append(f"  • {name}")

        if len(activity_names) > 10:
            lines.append(f"  ... 还有 {len(activity_names) - 10} 个")

        if failed_count > 0:
            lines.append(f"\n{failed_count} 个活动添加失败")

        logger.info(f"用户添加 {success_count} 个活动到忽略列表")

        return Response.text("\n".join(lines))
