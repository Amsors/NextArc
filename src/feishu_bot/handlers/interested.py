"""感兴趣指令处理器

处理用户发送的"感兴趣"指令，将已筛选掉的活动标记为感兴趣，
这些活动将绕过所有筛选（数据库/AI/时间筛选）。
"""

from src.core import UserPreferenceManager
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.interested")


class InterestedHandler(CommandHandler):
    """
    感兴趣指令处理器

    支持指令：
    - /interested ai 1,2,3
    - 感兴趣 时间 1-5
    - /interested 忽略 全部
    - /interested db 1,3-5,10

    处理格式：
    - "/interested <筛选类型> <序号>"
    - 筛选类型：ai, db/ignore/忽略, time/时间
    - 序号格式：1,2,3 或 1-5 或 1,3-5,10 或 全部
    """

    # 类级别的共享实例
    _user_preference_manager: UserPreferenceManager = None

    @classmethod
    def set_user_preference_manager(cls, manager: UserPreferenceManager) -> None:
        """设置用户偏好管理器"""
        cls._user_preference_manager = manager

    @property
    def command(self) -> str:
        return "interested"

    def get_usage(self) -> str:
        return (
            "/interested <筛选类型> <序号> - 将筛选掉的活动标记为感兴趣\n"
            "  筛选类型: ai, db/ignore/忽略, time/时间\n"
            "  序号格式: 1,2,3 或 1-5 或 全部"
        )

    async def handle(self, args: list[str], session: UserSession) -> Response:
        """
        处理 /interested 或 感兴趣 指令

        Args:
            args: 指令参数列表，如 ["ai", "1,2,3"] 或 ["时间", "1-5"]
            session: 用户会话

        Returns:
            回复消息
        """
        if not self._user_preference_manager:
            return Response.text("感兴趣功能未初始化")

        # 检查参数数量
        if len(args) < 2:
            return Response.text(
                "格式错误\n\n"
                "用法：\n"
                "• /interested ai 1,2,3 - 将AI筛选掉的第1、2、3个活动标记为感兴趣\n"
                "• /interested time 1-5 - 将时间筛选掉的第1到5个活动标记为感兴趣\n"
                "• /interested ignore 1,3-5 - 将数据库筛选掉的活动标记为感兴趣\n"
                "• /interested ai 全部 - 将AI筛选掉的全部活动标记为感兴趣\n"
                "\n筛选类型说明：\n"
                "• ai - AI筛选掉的活动\n"
                "• time/时间 - 时间筛选掉的活动\n"
                "• db/ignore/忽略 - 数据库筛选掉的活动\n"
                "\n被标记为感兴趣的活动将绕过所有筛选，在后续扫描中会被推荐"
            )

        # 解析筛选类型
        filter_type_arg = args[0].lower()
        filter_type = self._parse_filter_type(filter_type_arg)

        if not filter_type:
            return Response.text(
                f"未知的筛选类型: {args[0]}\n\n"
                "支持的筛选类型：\n"
                "• ai - AI筛选掉的活动\n"
                "• time/时间 - 时间筛选掉的活动\n"
                "• db/ignore/忽略 - 数据库筛选掉的活动"
            )

        # 合并序号参数（支持 "/interested ai 1 2 3" 或 "/interested ai 1,2,3"）
        indices_str = " ".join(args[1:]).strip()

        # 获取对应筛选类型的活动列表
        filtered_activities = session.get_filtered_activities_by_type(filter_type)

        if not filtered_activities:
            type_name = self._get_filter_type_name(filter_type)
            return Response.text(
                f"没有被{type_name}筛选掉的活动\n\n"
                "提示：只有在收到新活动通知后，才能使用该命令恢复被筛选的活动\n"
                "筛选信息显示在通知消息中，包含被各类筛选器过滤掉的活动列表"
            )

        # 解析序号
        indices, errors = self._parse_indices(indices_str, len(filtered_activities))

        if errors:
            error_msg = "\n".join(f"  • {e}" for e in errors)
            return Response.text(f"解析失败\n\n{error_msg}")

        if not indices:
            return Response.text(
                "没有有效的活动序号\n\n"
                f"有效范围：1-{len(filtered_activities)}"
            )

        # 获取要标记为感兴趣的活动ID
        activity_ids = []
        activity_names = []

        for idx in indices:
            # 序号从1开始，列表索引从0开始
            filtered_activity = filtered_activities[idx - 1]
            activity = filtered_activity.activity
            activity_ids.append(activity.id)
            activity_names.append(f"[{idx}] {activity.name}")

        if not activity_ids:
            return Response.text("无法获取活动信息，请重试")

        # 添加到感兴趣数据库
        success_count, failed_count = await self._user_preference_manager.add_interested_activities(activity_ids)

        if success_count == 0:
            return Response.text("添加失败，请稍后重试")

        # 构建回复消息
        type_name = self._get_filter_type_name(filter_type)
        lines = [f"已将 {success_count} 个{type_name}筛选掉的活动标记为感兴趣\n"]

        # 显示添加的活动
        lines.append("成功添加的活动：")
        for name in activity_names[:10]:  # 最多显示10个
            lines.append(f"  • {name}")

        if len(activity_names) > 10:
            lines.append(f"  ... 还有 {len(activity_names) - 10} 个")

        if failed_count > 0:
            lines.append(f"\n{failed_count} 个活动添加失败")

        logger.info(f"用户将 {success_count} 个被{type_name}筛选的活动标记为感兴趣")

        return Response.text("\n".join(lines))

    def _parse_filter_type(self, arg: str) -> str | None:
        """
        解析筛选类型参数

        Args:
            arg: 用户输入的筛选类型

        Returns:
            标准化的筛选类型（ai, db, time）或 None
        """
        ai_aliases = ["ai", "人工智能", "智能"]
        db_aliases = ["db", "ignore", "数据库", "忽略", "不感兴趣"]
        time_aliases = ["time", "时间", "时间筛选"]

        if arg in ai_aliases:
            return "ai"
        if arg in db_aliases:
            return "db"
        if arg in time_aliases:
            return "time"

        return None

    def _get_filter_type_name(self, filter_type: str) -> str:
        """
        获取筛选类型的中文名称

        Args:
            filter_type: 标准化的筛选类型

        Returns:
            中文名称
        """
        names = {
            "ai": "AI",
            "db": "数据库",
            "time": "时间",
        }
        return names.get(filter_type, filter_type)

    def _parse_indices(self, indices_str: str, max_index: int) -> tuple[list[int], list[str]]:
        """
        解析序号字符串

        Args:
            indices_str: 序号字符串（如 "1,2,3" 或 "1-5" 或 "全部"）
            max_index: 最大有效序号

        Returns:
            (有效的序号列表, 错误信息列表)
        """
        indices_str = indices_str.strip()

        # 处理"全部"或"所有"
        if indices_str in ["全部", "所有"]:
            return list(range(1, max_index + 1)), []

        indices = []
        errors = []

        # 按逗号分割
        parts = indices_str.split(",")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 检查是否是范围（如 "1-5"）
            if "-" in part:
                range_parts = part.split("-", 1)
                try:
                    start = int(range_parts[0].strip())
                    end = int(range_parts[1].strip())

                    if start > end:
                        start, end = end, start

                    # 验证范围
                    if start < 1 or end > max_index:
                        errors.append(f"范围 {part} 超出有效范围（1-{max_index}）")
                        continue

                    indices.extend(range(start, end + 1))

                except ValueError:
                    errors.append(f"无法解析范围: {part}")
                    continue
            else:
                # 单个数字
                try:
                    idx = int(part)
                    if idx < 1 or idx > max_index:
                        errors.append(f"序号 {idx} 超出有效范围（1-{max_index}）")
                        continue
                    indices.append(idx)
                except ValueError:
                    errors.append(f"无法解析序号: {part}")
                    continue

        # 去重并保持顺序
        seen = set()
        unique_indices = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        return unique_indices, errors
