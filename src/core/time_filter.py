"""时间筛选器"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

from pyustc.young import SecondClass

from src.config.preferences import PushPreferences, TimeRange
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("time_filter")


@dataclass
class TimeFilterDetail:
    """时间筛选的详细信息"""
    conflicting_ranges: list[TimeRange]


class TimeFilter:
    """根据用户配置的时间偏好筛选活动"""

    def __init__(self, preferences: Optional[PushPreferences] = None):
        if preferences is None:
            from src.config.preferences import load_preferences
            preferences = load_preferences()

        self.preferences = preferences
        self.time_config = preferences.time_filter

    def is_enabled(self) -> bool:
        """检查时间筛选是否启用"""
        return self.time_config.is_enabled_and_configured()

    def filter_activities(
            self,
            activities: list[SecondClass]
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        """筛选活动，返回不冲突和被过滤的活动列表"""
        if not self.is_enabled():
            logger.debug("时间筛选未启用，返回所有活动")
            return activities, []

        if not activities:
            return [], []

        logger.info(f"开始时间筛选，共 {len(activities)} 个活动...")

        passed = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            conflict_result = self._check_time_conflict(activity)
            if conflict_result is None:
                passed.append(activity)
            else:
                filtered.append(conflict_result)

        logger.info(f"时间筛选完成：{len(passed)} 个通过，{len(filtered)} 个被过滤")

        return passed, filtered

    def _check_time_conflict(self, activity: SecondClass) -> Optional[FilteredActivity]:
        """检查活动是否与用户没空时间冲突"""
        hold_time = activity.hold_time
        if hold_time is None:
            logger.debug(f"活动 '{activity.name}' 无法获取举办时间，保留")
            return None

        activity_start = hold_time.start
        if activity_start is None:
            logger.debug(f"活动 '{activity.name}' 无法获取开始时间，保留")
            return None

        weekday = activity_start.weekday()
        busy_ranges = self.time_config.weekly_preferences.get_day_preference(weekday)
        if not busy_ranges:
            return None

        act_start_time = activity_start.time()
        act_end_time = hold_time.end.time() if hold_time.end else None

        if act_end_time is None:
            act_end_time = (datetime.combine(datetime.today(), act_start_time) + timedelta(hours=2)).time()

        overlap_mode = self.time_config.overlap_mode
        conflicting_ranges = []

        for busy_range in busy_ranges:
            busy_start, busy_end = busy_range.to_time_objects()

            if overlap_mode == "partial":
                if act_start_time < busy_end and act_end_time > busy_start:
                    conflicting_ranges.append(busy_range)

            elif overlap_mode == "full":
                if busy_start <= act_start_time and act_end_time <= busy_end:
                    conflicting_ranges.append(busy_range)

            elif overlap_mode == "threshold":
                if act_start_time < busy_end and act_end_time > busy_start:
                    conflicting_ranges.append(busy_range)

        if conflicting_ranges:
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            day_name = day_names[weekday]
            ranges_str = ", ".join(str(r) for r in conflicting_ranges)

            if overlap_mode == "partial":
                overlap_desc = "时间冲突"
            elif overlap_mode == "full":
                overlap_desc = "时间完全被占用"
            else:
                overlap_ratio = self._calculate_overlap_ratio(
                    act_start_time, act_end_time, conflicting_ranges
                )
                threshold = self.time_config.overlap_threshold

                if overlap_ratio < threshold:
                    logger.debug(
                        f"活动 '{activity.name}' 重叠比例 {overlap_ratio:.2%} < 阈值 {threshold:.2%}，保留"
                    )
                    return None

                overlap_desc = f"时间冲突比例 {overlap_ratio:.1%} >= 阈值 {threshold:.1%}"

            reason = f"与{day_name}的{overlap_desc} ({ranges_str})"
            logger.debug(f"活动 '{activity.name}' {reason}")

            extra_data = {
                "conflicting_ranges": conflicting_ranges,
                "weekday": weekday,
                "day_name": day_name,
            }

            if overlap_mode == "threshold":
                extra_data["overlap_ratio"] = overlap_ratio
                extra_data["overlap_threshold"] = self.time_config.overlap_threshold

            return FilteredActivity(
                activity=activity,
                reason=reason,
                filter_type="time",
                extra_data=extra_data
            )

        return None

    def _calculate_overlap_ratio(
            self,
            act_start: time,
            act_end: time,
            busy_ranges: list[TimeRange]
    ) -> float:
        """计算活动时间与忙碌时间段的重叠比例"""
        today = datetime.today()
        act_start_dt = datetime.combine(today, act_start)
        act_end_dt = datetime.combine(today, act_end)

        if act_end_dt < act_start_dt:
            act_end_dt += timedelta(days=1)

        activity_duration = (act_end_dt - act_start_dt).total_seconds() / 60

        if activity_duration <= 0:
            return 0.0

        total_conflict_minutes = 0.0

        for busy_range in busy_ranges:
            busy_start, busy_end = busy_range.to_time_objects()
            busy_start_dt = datetime.combine(today, busy_start)
            busy_end_dt = datetime.combine(today, busy_end)

            overlap_start = max(act_start_dt, busy_start_dt)
            overlap_end = min(act_end_dt, busy_end_dt)

            if overlap_end > overlap_start:
                overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
                total_conflict_minutes += overlap_minutes

        overlap_ratio = total_conflict_minutes / activity_duration
        return min(overlap_ratio, 1.0)

    def get_filter_summary(self, filtered: list[FilteredActivity]) -> str:
        """生成被过滤活动的汇总信息"""
        if not filtered:
            return ""

        lines = [f"根据时间偏好，已过滤 {len(filtered)} 个冲突活动："]

        for i, item in enumerate(filtered, 1):
            activity = item.activity
            lines.append(f"[{i}] {activity.name}")

            if activity.hold_time and activity.hold_time.start:
                start = activity.hold_time.start
                end = activity.hold_time.end
                if end:
                    lines.append(
                        f"    活动时间：{start.strftime('%m-%d(%a) %H:%M')} ~ {end.strftime('%H:%M')}, {item.reason}")
                else:
                    lines.append(f"    活动时间：{start.strftime('%m-%d(%a) %H:%M')}, {item.reason}")

        return "\n".join(lines)

    def get_preferences_summary(self) -> str:
        """获取当前时间偏好配置的摘要"""
        if not self.is_enabled():
            return "时间筛选：未启用"

        lines = ["时间筛选：已启用", "", "您配置的不方便时间段：",
                 self.time_config.weekly_preferences.format_preferences()]

        return "\n".join(lines)


def create_time_filter_from_config() -> TimeFilter:
    """从配置创建时间筛选器实例"""
    from src.config.preferences import load_preferences

    preferences = load_preferences()
    return TimeFilter(preferences)
