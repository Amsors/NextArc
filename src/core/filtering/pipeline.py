"""统一活动筛选管线。"""

from typing import TYPE_CHECKING

from pyustc.young import SecondClass

from src.core.enrolled_filter import EnrolledFilter
from src.core.overlay_filter import OverlayFilter
from src.core.repositories import ActivityRepository
from src.models.secondclass_view import get_status_text
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

from .context import FilterContext
from .result import FilterPipelineResult

if TYPE_CHECKING:
    from src.core.ai_filter import AIFilter
    from src.core.time_filter import TimeFilter
    from src.core.user_preference_manager import UserPreferenceManager

logger = get_logger("filtering.pipeline")


class ActivityFilterPipeline:
    """复用 scanner 和指令入口的活动筛选流程。"""

    def __init__(
        self,
        *,
        activity_repository: ActivityRepository | None = None,
        user_preference_manager: "UserPreferenceManager | None" = None,
        ai_filter: "AIFilter | None" = None,
        use_ai_filter: bool = False,
        ai_user_info: str = "",
        time_filter: "TimeFilter | None" = None,
        use_time_filter: bool = False,
    ):
        self.activity_repository = activity_repository or ActivityRepository()
        self.user_preference_manager = user_preference_manager
        self.ai_filter = ai_filter
        self.use_ai_filter = use_ai_filter
        self.ai_user_info = ai_user_info
        self.time_filter = time_filter
        self.use_time_filter = use_time_filter

    async def apply(
        self,
        activities: list[SecondClass],
        context: FilterContext,
    ) -> FilterPipelineResult:
        filtered: dict[str, list[FilteredActivity]] = {
            "status": [],
            "enrolled": [],
            "db": [],
            "overlay": [],
            "time": [],
            "ai": [],
        }
        summaries: list[str] = []
        restored: list[SecondClass] = []
        ai_keep_reasons: dict[str, str] = {}
        overlap_reasons: dict[str, str] = {}

        activities, filtered["status"] = self._filter_by_status(activities, context)

        if context.apply_enrolled_filter:
            enrolled_ids = await self.activity_repository.list_enrolled_ids(context.latest_db)
            if enrolled_ids:
                activities, filtered["enrolled"] = EnrolledFilter(enrolled_ids).filter_activities(activities)

        if not context.enable_filters:
            summaries.extend(self._build_summaries(filtered, overlap_reasons, restored))
            return FilterPipelineResult(
                kept=activities,
                filtered=filtered,
                restored=restored,
                ai_keep_reasons=ai_keep_reasons,
                overlap_reasons=overlap_reasons,
                summaries=summaries,
            )

        if context.include_interested_restore and self.user_preference_manager:
            activities, restored = await self.user_preference_manager.restore_interested_activities(activities)

        if self.user_preference_manager:
            activities, filtered["db"] = await self._filter_ignored_only(activities)

        enrolled_time_ranges = await self.activity_repository.list_enrolled_time_ranges(context.latest_db)
        if enrolled_time_ranges:
            overlay_filter = OverlayFilter(enrolled_time_ranges)
            activities, filtered["overlay"] = overlay_filter.filter_activities(
                activities,
                ignore_overlap=context.ignore_overlap,
            )
            overlap_reasons = overlay_filter.overlap_reasons
        else:
            logger.debug("没有已报名活动时间记录，跳过重叠筛选")

        if self.use_time_filter and self.time_filter:
            activities, filtered["time"] = self.time_filter.filter_activities(activities)

        if self.use_ai_filter and self.ai_filter and self.ai_user_info:
            prefer_cached = context.use_ai_cache and not context.force_ai_review
            activities, filtered["ai"], ai_keep_reasons = await self.ai_filter.filter_activities(
                activities,
                self.ai_user_info,
                write_to_db=True,
                prefer_cached=prefer_cached,
                preference_manager=self.user_preference_manager,
            )
        else:
            logger.debug(
                "跳过 AI 筛选: use_ai_filter=%s, has_ai_filter=%s, has_user_info=%s",
                self.use_ai_filter,
                self.ai_filter is not None,
                bool(self.ai_user_info),
            )

        kept = restored + activities
        summaries.extend(self._build_summaries(filtered, overlap_reasons, restored))

        return FilterPipelineResult(
            kept=kept,
            filtered=filtered,
            restored=restored,
            ai_keep_reasons=ai_keep_reasons,
            overlap_reasons=overlap_reasons,
            summaries=summaries,
        )

    def _filter_by_status(
        self,
        activities: list[SecondClass],
        context: FilterContext,
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        allowed_codes = context.allowed_status_codes()
        if allowed_codes is None:
            return activities, []

        kept: list[SecondClass] = []
        filtered: list[FilteredActivity] = []
        for activity in activities:
            status = getattr(activity, "status", None)
            status_code = getattr(status, "code", status)

            try:
                code = int(status_code)
            except (TypeError, ValueError):
                code = None

            if code in allowed_codes:
                kept.append(activity)
            else:
                filtered.append(
                    FilteredActivity(
                        activity=activity,
                        reason=f"活动状态不可展示：{get_status_text(activity)}",
                        filter_type="status",
                    )
                )

        if filtered:
            logger.info("状态筛选过滤了 %s 个活动", len(filtered))
        return kept, filtered

    async def _filter_ignored_only(
        self,
        activities: list[SecondClass],
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        if not activities or not self.user_preference_manager:
            return activities, []

        ignored_ids = await self.user_preference_manager.get_all_ignored_ids()
        if not ignored_ids:
            return activities, []

        kept: list[SecondClass] = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            activity_id = getattr(activity, "id", None)
            if activity_id in ignored_ids:
                filtered.append(
                    FilteredActivity(
                        activity=activity,
                        reason="用户已标记为不感兴趣",
                        filter_type="ignore",
                    )
                )
            else:
                kept.append(activity)

        if filtered:
            logger.info("数据库筛选过滤了 %s 个活动", len(filtered))
        return kept, filtered

    @staticmethod
    def _build_summaries(
        filtered: dict[str, list[FilteredActivity]],
        overlap_reasons: dict[str, str],
        restored: list[SecondClass],
    ) -> list[str]:
        summaries: list[str] = []

        if filtered.get("status"):
            summaries.append(f"状态筛选已过滤 {len(filtered['status'])} 个活动")
        if filtered.get("enrolled"):
            summaries.append(f"已报名筛选已过滤 {len(filtered['enrolled'])} 个活动")
        if restored:
            summaries.append(f"感兴趣白名单已恢复 {len(restored)} 个活动")
        if filtered.get("db"):
            summaries.append(f"数据库筛选已过滤 {len(filtered['db'])} 个不感兴趣的活动")
        if filtered.get("overlay"):
            summaries.append(f"重叠筛选已过滤 {len(filtered['overlay'])} 个活动")
        if overlap_reasons:
            summaries.append(f"重叠筛选标记了 {len(overlap_reasons)} 个活动但仍保留")
        if filtered.get("time"):
            summaries.append(f"时间筛选已过滤 {len(filtered['time'])} 个活动")
        if filtered.get("ai"):
            summaries.append(f"AI 筛选已过滤 {len(filtered['ai'])} 个活动")

        return summaries
