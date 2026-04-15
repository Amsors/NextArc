"""/valid 指令处理器"""

import aiosqlite
from pyustc.young import SecondClass, Status

from src.core import EnrolledFilter, OverlayFilter, UserPreferenceManager
from src.models import UserSession, secondclass_from_db_row
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.valid")


class ValidHandler(CommandHandler):
    _user_preference_manager: UserPreferenceManager = None

    @classmethod
    def set_ignore_manager(cls, user_preference_manager: UserPreferenceManager) -> None:
        cls._user_preference_manager = user_preference_manager

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

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        need_rescan = "重新扫描" in args
        show_all = "全部" in args or "所有" in args
        deep_update = "深度" in args or "深度更新" in args
        ai_filter_again = "重新筛选" in args

        logger.info(f"执行 /valid 指令，重新扫描={need_rescan}, 显示全部={show_all}, 深度更新={deep_update}")

        scan_info = ""

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
                    return Response.error(error, context="重新扫描")

                scan_info = format_scan_result(result)

            except Exception as e:
                logger.error(f"重新扫描失败: {e}")
                return Response.error(str(e), context="重新扫描")

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("暂无数据，请先执行 /update 或 /valid 重新扫描")

        try:
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
                lines = ["可报名活动\n\n目前暂无可报名的活动"]
                if need_rescan:
                    lines.insert(0, scan_info)
                    lines.insert(1, "")
                return Response.text("\n".join(lines))

            original_count = len(activities)
            filter_info = []
            db_filtered = []
            time_filtered = []
            ai_filtered = []
            enrolled_filtered = []
            overlay_filtered = []
            ai_keep_reasons = {}

            if not show_all:
                enrolled_ids = await EnrolledFilter.get_enrolled_ids_from_db(latest_db)
                if enrolled_ids:
                    enrolled_filter = EnrolledFilter(enrolled_ids)
                    activities, enrolled_filtered = enrolled_filter.filter_activities(activities)
                    if enrolled_filtered:
                        filter_info.append(f"已报名筛选已过滤 {len(enrolled_filtered)} 个活动")
                        logger.info(f"已报名筛选过滤了 {len(enrolled_filtered)} 个活动")

                if self._user_preference_manager:
                    activities, db_filtered = await self._user_preference_manager.filter_activities(activities)
                    if db_filtered:
                        filter_info.append(f"数据库筛选已过滤 {len(db_filtered)} 个不感兴趣的活动")
                        logger.info(f"数据库筛选过滤了 {len(db_filtered)} 个活动")

                enrolled_time_ranges = await OverlayFilter.get_enrolled_time_ranges_from_db(latest_db)
                overlap_reasons: dict[str, str] = {}
                if enrolled_time_ranges:
                    from src.config import get_settings
                    ignore_overlap = get_settings().filter.ignore_overlap
                    overlay_filter = OverlayFilter(enrolled_time_ranges)
                    activities, overlay_filtered = overlay_filter.filter_activities(
                        activities, ignore_overlap=ignore_overlap
                    )
                    overlap_reasons = overlay_filter.overlap_reasons
                    if overlay_filtered:
                        filter_info.append(f"重叠筛选已过滤 {len(overlay_filtered)} 个活动")
                        logger.info(f"重叠筛选过滤了 {len(overlay_filtered)} 个活动")
                    if overlap_reasons:
                        filter_info.append(f"重叠筛选标记了 {len(overlap_reasons)} 个活动但仍保留")
                        logger.info(f"重叠筛选标记了 {len(overlap_reasons)} 个活动但仍保留")
                else:
                    logger.debug("没有已报名活动时间记录，跳过重叠筛选")

                if self._scanner.use_time_filter and self._scanner.time_filter:
                    activities, time_filtered = self._scanner.time_filter.filter_activities(activities)
                    if time_filtered:
                        filter_info.append(f"时间筛选已过滤 {len(time_filtered)} 个活动")
                        logger.info(f"时间筛选过滤了 {len(time_filtered)} 个活动")

                if self._scanner.use_ai_filter and self._scanner.ai_filter and self._scanner.ai_user_info:
                    ai_user_info = self._scanner.ai_user_info
                    activities, ai_filtered, ai_keep_reasons = await self._scanner.ai_filter.filter_activities(
                        activities,
                        ai_user_info,
                        write_to_db=True,
                        prefer_cached=not ai_filter_again,
                        preference_manager=self._user_preference_manager,
                    )
                    ai_filtered_count = len(ai_filtered)
                    if ai_filtered_count > 0:
                        filter_info.append(f"AI 筛选已过滤 {ai_filtered_count} 个活动")
                        logger.info(f"AI 筛选过滤了 {ai_filtered_count} 个活动")
                    logger.debug(f"/valid AI筛选保留原因: {ai_keep_reasons}")
                else:
                    logger.debug(f"/valid 跳过AI筛选: use_ai_filter={self._scanner.use_ai_filter}, "
                                f"has_ai_filter={self._scanner.ai_filter is not None}, "
                                f"has_user_info={bool(self._scanner.ai_user_info)}")

            filter_result = dict()
            if ai_filtered:
                filter_result["ai"] = ai_filtered
            if db_filtered:
                filter_result["db"] = db_filtered
            if time_filtered:
                filter_result["time"] = time_filtered
            if enrolled_filtered:
                filter_result["enrolled"] = enrolled_filtered
            if overlay_filtered:
                filter_result["overlay"] = overlay_filtered

            session.set_displayed_activities(
                activities=activities,
                source="valid",
                filtered_activities=filter_result
            )

            if not activities:
                lines = []
                if need_rescan:
                    lines.append(scan_info)
                    lines.append("")

                lines.append(f"可报名活动（共 {original_count} 条，已筛选）：")
                for info in filter_info:
                    lines.append(f"  {info}")
                lines.append("")
                lines.append("筛选后暂无可报名的活动")
                if not show_all:
                    lines.append("发送「/valid 全部」查看所有活动（不进行筛选）")
                return Response.text("\n".join(lines))

            lines = []
            if need_rescan:
                lines.append(scan_info)
                lines.append("")

            if show_all:
                lines.append(f"可报名活动（共 {original_count} 条，显示全部）：")
            else:
                if filter_info:
                    lines.append(f"可报名活动（共 {original_count} 条，已筛选）：")
                    for info in filter_info:
                        lines.append(f"  {info}")
                else:
                    lines.append(f"可报名活动（共 {original_count} 条）：")

            lines.append("")
            lines.append(f"已发送 {len(activities)} 个可报名活动的卡片")
            lines.append("（使用折叠面板展示，点击活动名称查看详情）")

            if not show_all:
                has_filter = (
                        self._scanner.use_ai_filter or
                        self._scanner.use_time_filter or
                        self._user_preference_manager or
                        True
                )
                if has_filter:
                    lines.append("发送「/valid 全部」查看所有活动（不进行筛选）")

            lines.append("对活动不感兴趣？发送「不感兴趣 序号」或「不感兴趣 全部」")

            from src.config import get_settings
            feishu_config = get_settings().feishu
            card_ai_reasons = ai_keep_reasons if feishu_config.send_ai_filter_detail.kept else None
            logger.info(f"/valid 卡片配置: kept={feishu_config.send_ai_filter_detail.kept}, "
                       f"ai_keep_reasons_keys={list(card_ai_reasons.keys()) if card_ai_reasons else []}")

            return Response.activity_list(
                activities=activities,
                title=f"可报名活动（共 {len(activities)} 个）",
                filters_applied=filter_info,
                hint="\n".join(lines),
                ai_reasons=card_ai_reasons,
                overlap_reasons=overlap_reasons if overlap_reasons else None,
            )

        except Exception as e:
            logger.error(f"查询可报名活动失败: {e}")
            import traceback
            traceback.print_exc()
            return Response.error(str(e), context="查询可报名活动")

    async def _get_valid_activities(self, db_path) -> list[SecondClass]:
        activities = []

        valid_status_codes = [Status.APPLYING.code, Status.PUBLISHED.code]

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
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
