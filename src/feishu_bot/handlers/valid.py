"""/valid 指令处理器"""

from pyustc.young import SecondClass

from src.core import FilterContext, UserPreferenceManager
from src.core.repositories import ActivityRepository
from src.core.services import ActivityQueryService
from src.models import UserSession
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
                update_service = self._activity_update_service
                if update_service is None:
                    from src.core.services import ActivityUpdateService
                    update_service = ActivityUpdateService(self._auth_manager)

                update_result = await update_service.update_activities(
                    activities,
                    continue_on_error=True,
                )
                if update_result.failed:
                    logger.warning(f"/valid 深度更新失败 {update_result.failed_count} 个活动")

            if not activities:
                lines = ["可报名活动\n\n目前暂无可报名的活动"]
                if need_rescan:
                    lines.insert(0, scan_info)
                    lines.insert(1, "")
                return Response.text("\n".join(lines))

            original_count = len(activities)
            pipeline = self._scanner.filter_pipeline
            pipeline_result = await pipeline.apply(
                activities,
                FilterContext(
                    latest_db=latest_db,
                    enable_filters=not show_all,
                    include_interested_restore=not show_all,
                    use_ai_cache=not ai_filter_again,
                    force_ai_review=ai_filter_again,
                    ignore_overlap=self._scanner.ignore_overlap,
                    source="valid",
                    apply_enrolled_filter=not show_all,
                ),
            )
            activities = pipeline_result.kept
            filter_info = pipeline_result.summaries
            filter_result = pipeline_result.non_empty_filtered()
            ai_keep_reasons = pipeline_result.ai_keep_reasons
            overlap_reasons = pipeline_result.overlap_reasons

            await session.context_manager.set_displayed_activities(
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
        service = self._activity_query_service or ActivityQueryService(ActivityRepository())
        activities = await service.list_valid_activities(db_path)
        logger.debug(f"从数据库获取到 {len(activities)} 个可报名活动")
        return activities
