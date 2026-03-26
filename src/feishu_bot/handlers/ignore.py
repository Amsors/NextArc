"""不感兴趣指令处理器

处理用户发送的"不感兴趣"指令，将活动加入忽略数据库
"""

from src.core import UserPreferenceManager
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.ignore")


class IgnoreHandler(CommandHandler):
    """
    不感兴趣指令处理器
    
    支持指令：
    - /ignore 1,2,3
    - 不感兴趣 1-5
    - 不感兴趣 全部
    
    处理格式：
    - "不感兴趣 1,2,3" - 忽略序号为1,2,3的活动
    - "不感兴趣 1-5" - 忽略序号1到5的活动
    - "不感兴趣 1,3-5,10" - 组合格式
    - "不感兴趣 全部" 或 "不感兴趣 所有" - 忽略所有上次显示的活动
    """

    # 类级别的共享实例
    _ignore_manager: UserPreferenceManager = None

    @classmethod
    def set_ignore_manager(cls, ignore_manager: UserPreferenceManager) -> None:
        """设置忽略管理器"""
        cls._ignore_manager = ignore_manager

    @property
    def command(self) -> str:
        return "ignore"

    def get_usage(self) -> str:
        return (
            "/ignore <序号> 或 不感兴趣 <序号> - 将活动加入忽略列表\n"
            "  序号格式: 1,2,3 或 1-5 或 全部"
        )

    async def handle(self, args: list[str], session: UserSession) -> Response:
        """
        处理 /ignore 或 不感兴趣 指令

        Args:
            args: 指令参数列表
            session: 用户会话

        Returns:
            回复消息
        """
        if not self._ignore_manager:
            return Response.text("忽略功能未初始化")

        # 检查参数
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
            ai_filtered_activities = session.get_filtered_activities_by_type("ai")

            if not ai_filtered_activities:
                return Response.text("没有AI忽略的活动")

            ai_filtered_activities_ids = [activity.activity_id for activity in ai_filtered_activities]

            success_count, failed_count = await self._ignore_manager.add_ignored_activities(ai_filtered_activities_ids)

            if failed_count != 0:
                return Response.text(f"添加失败，{failed_count}个活动未添加, {success_count}个活动成功添加")

            return Response.text(f"已添加AI筛选出的{success_count}个活动到不感兴趣列表")

        # 合并参数（支持 "不感兴趣 1 2 3" 或 "不感兴趣 1,2,3"）
        indices_str = " ".join(args).strip()

        # 检查是否有可操作的最近活动列表
        displayed_activities = session.get_all_displayed_activities()

        # filtered_displayed_activities = session.get_filtered_activities()

        if not displayed_activities:
            return Response.text(
                "没有可操作的最近活动列表\n\n"
                "请先用以下指令查看活动：\n"
                "• /valid - 查看可报名活动\n"
                "• /search <关键词> - 搜索活动"
            )

        # 解析序号
        indices, errors = session.parse_displayed_indices(indices_str)

        if errors:
            error_msg = "\n".join(f"  • {e}" for e in errors)
            return Response.text(f"解析失败\n\n{error_msg}")

        if not indices:
            return Response.text(
                "没有有效的活动序号\n\n"
                f"有效范围：1-{len(displayed_activities)}"
            )

        # 获取要忽略的活动ID
        activity_ids = []
        activity_names = []

        for idx in indices:
            activity = session.get_displayed_activity_by_index(idx)
            if activity:
                activity_ids.append(activity.id)
                activity_names.append(f"[{idx}] {activity.name}")

        if not activity_ids:
            return Response.text("无法获取活动信息，请重试")

        # 添加到忽略数据库
        success_count, failed_count = await self._ignore_manager.add_ignored_activities(activity_ids)

        if success_count == 0:
            return Response.text("添加失败，请稍后重试")

        # 构建回复消息
        lines = ["已添加到不感兴趣列表\n"]

        # 显示添加的活动
        lines.append(f"成功添加 {success_count} 个活动：")
        for name in activity_names[:10]:  # 最多显示10个
            lines.append(f"  • {name}")

        if len(activity_names) > 10:
            lines.append(f"  ... 还有 {len(activity_names) - 10} 个")

        if failed_count > 0:
            lines.append(f"\n{failed_count} 个活动添加失败")

        logger.info(f"用户添加 {success_count} 个活动到忽略列表")

        return Response.text("\n".join(lines))
