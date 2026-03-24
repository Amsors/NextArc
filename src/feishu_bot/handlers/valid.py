"""/valid 指令处理器

显示当前数据库中可报名的所有第二课堂活动
"""

import aiosqlite
from pyustc.young import SecondClass, Status

from src.core import IgnoreManager
from src.models import UserSession, secondclass_from_db_row
from src.utils.formatter import build_activity_card
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.valid")


class ValidHandler(CommandHandler):
    """查询可报名活动指令"""

    # 类级别的忽略管理器
    _ignore_manager: IgnoreManager = None
    # 类级别的卡片发送回调
    _send_card_callback = None

    @classmethod
    def set_ignore_manager(cls, ignore_manager: IgnoreManager) -> None:
        """设置忽略管理器"""
        cls._ignore_manager = ignore_manager

    @classmethod
    def set_card_sender(cls, send_card_callback) -> None:
        """设置卡片发送回调"""
        cls._send_card_callback = send_card_callback

    @property
    def command(self) -> str:
        return "valid"

    def get_usage(self) -> str:
        return (
            "/valid [重新扫描] [全部] - 显示可报名的活动\n"
            "  重新扫描 - 先更新数据库再查询\n"
            "  全部 - 显示所有活动（不启用 AI/时间/数据库筛选）\n"
            "  深度 - 深度更新活动信息"
        )

    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /valid 指令"""
        if not self.check_dependencies():
            return "服务未初始化，请稍后重试"

        # 解析参数
        need_rescan = "重新扫描" in args
        show_all = "全部" in args or "所有" in args
        deep_update = "深度" in args or "深度更新" in args

        logger.info(f"执行 /valid 指令，重新扫描={need_rescan}, 显示全部={show_all}, 深度更新={deep_update}")

        # 如果需要重新扫描，先执行扫描
        if need_rescan:
            from src.utils.formatter import format_scan_result

            try:
                result = await self._scanner.scan(
                    deep_update=False,
                    notify_diff=False,
                    notify_enrolled_change=False,
                    notify_new_activities=False,
                    no_filter=True,
                )

                if not result["success"]:
                    error = result.get("error", "未知错误")
                    return f"❌ 重新扫描失败：{error}"

                scan_info = format_scan_result(result)

            except Exception as e:
                logger.error(f"重新扫描失败: {e}")
                return f"❌ 重新扫描失败：{str(e)}"

        # 获取最新数据库
        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return "❌ 暂无数据，请先执行 /update 或 /valid 重新扫描"

        try:
            # 从数据库获取可报名活动（状态为 PUBLISHED 或 APPLYING）
            activities = await self._get_valid_activities(latest_db)

            if deep_update:
                async with self._auth_manager.create_session_once() as service:
                    for activity in activities:
                        try:
                            await activity.update()
                            logger.debug(f"更新活动信息成功: {activity.name}")
                        except Exception as e:
                            logger.warning(f"更新活动 {activity.id} 信息失败: {e}")

            if not activities:
                msg = "📋 可报名活动\n\n目前暂无可报名的活动"
                if need_rescan:
                    msg = f"{scan_info}\n\n{msg}"
                return msg

            # 保存原始数量用于后续显示
            original_count = len(activities)
            filter_info = []

            # 如果不显示全部，则应用筛选器
            if not show_all:

                # 应用数据库筛选（被用户标记为不感兴趣的活动）
                if self._ignore_manager:
                    db_filtered = []
                    activities, db_filtered = await self._ignore_manager.filter_activities(activities)
                    if db_filtered:
                        filter_info.append(f"🗑️ 数据库筛选已过滤 {len(db_filtered)} 个不感兴趣的活动")
                        logger.info(f"数据库筛选过滤了 {len(db_filtered)} 个活动")

                # 应用时间筛选（如果启用）
                if self._scanner.use_time_filter and self._scanner.time_filter:
                    time_filtered = []
                    activities, filtered_result = self._scanner.time_filter.filter_activities(activities)
                    if filtered_result:
                        filter_info.append(f"⏰ 时间筛选已过滤 {len(filtered_result)} 个活动")
                        logger.info(f"时间筛选过滤了 {len(filtered_result)} 个活动")

                # 应用 AI 筛选（如果启用）
                if self._scanner.use_ai_filter and self._scanner.ai_filter:
                    ai_user_info = self._scanner.ai_user_info
                    ai_filtered = []
                    activities = await self._scanner.ai_filter.filter_activities(
                        activities,
                        ai_user_info,
                        uninterested_activities=ai_filtered
                    )
                    ai_filtered_count = len(ai_filtered)
                    if ai_filtered_count > 0:
                        filter_info.append(f"🤖 AI 筛选已过滤 {ai_filtered_count} 个活动")
                        logger.info(f"AI 筛选过滤了 {ai_filtered_count} 个活动")

            # 构建消息
            lines = []

            # 如果有重新扫描信息，先显示
            if need_rescan:
                lines.append(scan_info)
                lines.append("")

            # 标题和筛选信息
            if show_all:
                lines.append(f"📋 可报名活动（共 {original_count} 条，显示全部）：")
            else:
                if filter_info:
                    lines.append(f"📋 可报名活动（共 {original_count} 条，已筛选）：")
                    for info in filter_info:
                        lines.append(f"  {info}")
                else:
                    lines.append(f"📋 可报名活动（共 {original_count} 条）：")

            # 如果没有通过筛选的活动
            if not activities:
                lines.append("")
                lines.append("🤷 筛选后暂无可报名的活动")
                if not show_all:
                    lines.append("💡 发送「/valid 全部」查看所有活动（不进行筛选）")
                return "\n".join(lines)

            # 保存显示的活动列表到会话（用于"不感兴趣"功能）
            session.set_displayed_activities(activities, source="valid")

            # 发送折叠卡片形式的活动列表
            if activities and self._send_card_callback:
                try:
                    card_title = f"📋 可报名活动（共 {len(activities)} 个）"
                    card_content = build_activity_card(activities, card_title)
                    # 异步发送卡片
                    import asyncio
                    asyncio.create_task(self._send_card_callback(card_content))
                    logger.info(f"已发送活动卡片: {len(activities)} 个活动")
                except Exception as e:
                    logger.error(f"发送活动卡片失败: {e}")

            # 添加文本提示信息
            lines.append("")
            lines.append(f"📋 已发送 {len(activities)} 个可报名活动的卡片")
            lines.append("（使用折叠面板展示，点击活动名称查看详情）")

            # 提示信息
            if not show_all:
                has_filter = (
                        self._scanner.use_ai_filter or
                        self._scanner.use_time_filter or
                        self._ignore_manager
                )
                if has_filter:
                    lines.append("💡 发送「/valid 全部」查看所有活动（不进行筛选）")

            # 添加不感兴趣提示
            lines.append("🗑️ 对活动不感兴趣？发送「不感兴趣 序号」或「不感兴趣 全部」")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"查询可报名活动失败: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ 查询失败：{str(e)}"

    async def _get_valid_activities(self, db_path) -> list[SecondClass]:
        """从数据库获取可报名的活动（状态为 PUBLISHED 或 APPLYING）"""
        activities = []

        valid_status_codes = [Status.APPLYING.code, Status.PUBLISHED.code]

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            # 查询状态为发布中或报名中的活动
            placeholders = ",".join(["?"] * len(valid_status_codes))
            async with conn.execute(
                    f"""
                SELECT * FROM all_secondclass 
                WHERE status IN ({placeholders})
                ORDER BY name
                """,
                    valid_status_codes
            ) as cursor:
                async for row in cursor:
                    activities.append(secondclass_from_db_row(dict(row)))

        logger.debug(f"从数据库获取到 {len(activities)} 个可报名活动")
        return activities
