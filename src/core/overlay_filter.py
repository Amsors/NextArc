"""已有活动重叠筛选器"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from pyustc.young import SecondClass

from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("overlay_filter")


@dataclass
class EnrolledActivityTime:
    start: datetime
    end: datetime | None
    name: str


class OverlayFilter:
    def __init__(self, enrolled_time_ranges: Optional[list[EnrolledActivityTime]] = None):
        self.enrolled_time_ranges = enrolled_time_ranges or []
        self.overlap_reasons: dict[str, str] = {}

    def set_enrolled_time_ranges(self, enrolled_time_ranges: list[EnrolledActivityTime]) -> None:
        self.enrolled_time_ranges = enrolled_time_ranges

    def filter_activities(
            self,
            activities: list[SecondClass],
            ignore_overlap: bool = False,
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        if not activities:
            return [], []

        if not self.enrolled_time_ranges:
            logger.debug("没有已报名活动时间记录，跳过重叠筛选")
            return activities, []

        logger.info(
            f"开始重叠筛选，共 {len(activities)} 个活动，"
            f"已报名时间记录 {len(self.enrolled_time_ranges)} 个，"
            f"ignore_overlap={ignore_overlap}"
        )

        self.overlap_reasons = {}
        passed = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            # 系列活动不进入时间重叠筛选
            if getattr(activity, 'is_series', False):
                passed.append(activity)
                continue

            overlap_result = self._check_time_overlap(activity)
            if overlap_result is None:
                passed.append(activity)
            else:
                if ignore_overlap:
                    filtered.append(overlap_result)
                else:
                    self.overlap_reasons[activity.id] = overlap_result.reason
                    passed.append(activity)

        logger.info(f"重叠筛选完成：{len(passed)} 个通过，{len(filtered)} 个被过滤")
        if self.overlap_reasons:
            logger.info(f"有 {len(self.overlap_reasons)} 个活动被标记为时间重叠但仍保留")

        return passed, filtered

    def _check_time_overlap(self, activity: SecondClass) -> Optional[FilteredActivity]:
        hold_time = activity.hold_time
        if hold_time is None:
            logger.debug(f"活动 '{activity.name}' 无法获取举办时间，保留")
            return None

        activity_start = hold_time.start
        activity_end = hold_time.end

        if activity_start is None:
            logger.debug(f"活动 '{activity.name}' 无法获取开始时间，保留")
            return None

        overlaps: list[EnrolledActivityTime] = []

        for enrolled in self.enrolled_time_ranges:
            enrolled_start = enrolled.start
            enrolled_end = enrolled.end
            effective_enrolled_end = enrolled_end or (enrolled_start + timedelta(hours=2))
            effective_activity_end = activity_end or (activity_start + timedelta(hours=2))

            # 对于跨天（如系列活动）的已报名活动，不应用精确时间重叠筛选，
            # 因为无法判断系列课程在每一天的具体时间安排
            if effective_enrolled_end.date() != enrolled_start.date():
                logger.debug(
                    f"活动 '{activity.name}' 遇到跨天已报名活动"
                    f"（{enrolled.name}: {enrolled_start.strftime('%m-%d %H:%M')} ~ {effective_enrolled_end.strftime('%m-%d %H:%M')}），"
                    f"跳过精确重叠检查"
                )
                continue

            if activity_start < effective_enrolled_end and effective_activity_end > enrolled_start:
                overlaps.append(enrolled)

        if overlaps:
            reason = self._format_overlap_reason(overlaps)
            logger.debug(f"活动 '{activity.name}' {reason}")
            return FilteredActivity(
                activity=activity,
                reason=reason,
                filter_type="overlay"
            )

        return None

    @staticmethod
    def _format_overlap_reason(overlaps: list[EnrolledActivityTime]) -> str:
        lines = ["与已报名活动时间重叠："]
        for enrolled in overlaps:
            time_str = enrolled.start.strftime('%m-%d %H:%M')
            if enrolled.end:
                if enrolled.end.date() != enrolled.start.date():
                    time_str += f" ~ {enrolled.end.strftime('%m-%d %H:%M')}"
                else:
                    time_str += f" ~ {enrolled.end.strftime('%H:%M')}"
            lines.append(f"• {enrolled.name}（{time_str}）")
        return "\n".join(lines)

    @staticmethod
    async def get_enrolled_time_ranges_from_db(db_path) -> list[EnrolledActivityTime]:
        import aiosqlite

        time_ranges: list[EnrolledActivityTime] = []
        now = datetime.now()

        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                        "SELECT hold_time, name FROM enrolled_secondclass"
                ) as cursor:
                    async for row in cursor:
                        hold_time_json = row[0]
                        activity_name = row[1] or "未知活动"
                        if not hold_time_json:
                            continue
                        try:
                            data = json.loads(hold_time_json)
                            if not isinstance(data, dict):
                                logger.warning(f"已报名活动时间格式异常（期望字典）: {hold_time_json}")
                                continue
                            start_str = data.get("start")
                            end_str = data.get("end")
                            start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S") if start_str else None
                            end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S") if end_str else None
                            if start_dt:
                                effective_end = end_dt or (start_dt + timedelta(hours=2))
                                # 过滤掉已经结束超过1天的历史记录，避免干扰
                                if effective_end < now - timedelta(days=1):
                                    continue
                                time_ranges.append(EnrolledActivityTime(
                                    start=start_dt, end=end_dt, name=activity_name
                                ))
                        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
                            logger.warning(f"解析已报名活动时间失败: {e}, 数据={hold_time_json}")
                            continue

            logger.debug(f"从数据库获取到 {len(time_ranges)} 个有效已报名活动时间")

        except Exception as e:
            logger.error(f"获取已报名活动时间列表失败: {e}")

        return time_ranges
