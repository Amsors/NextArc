"""时间筛选器

根据用户配置的时间偏好，筛选出与用户没空时间冲突的活动。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from pyustc.young import SecondClass

from src.config.preferences import PushPreferences, TimeRange
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("time_filter")


@dataclass
class TimeFilterDetail:
    """时间筛选的详细信息，用于 FilteredActivity.extra_data"""
    conflicting_ranges: list[TimeRange]  # 冲突的时间段


class TimeFilter:
    """
    时间筛选器
    
    根据用户的推送偏好配置，筛选出与用户没空时间冲突的活动。
    """

    def __init__(self, preferences: Optional[PushPreferences] = None):
        """
        初始化时间筛选器
        
        Args:
            preferences: 推送偏好配置，如果为 None 则加载默认配置
        """
        if preferences is None:
            from src.config.preferences import load_preferences
            preferences = load_preferences()

        self.preferences = preferences
        self.time_config = preferences.time_filter

    def is_enabled(self) -> bool:
        """检查时间筛选是否启用且有配置"""
        return self.time_config.is_enabled_and_configured()

    def filter_activities(
            self,
            activities: list[SecondClass]
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        """
        筛选活动，返回不冲突的活动列表和被过滤的活动列表
        
        Args:
            activities: 待筛选的活动列表
            
        Returns:
            (通过筛选的活动列表, 被过滤的 FilteredActivity 列表)
        """
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
        """
        检查活动是否与用户没空时间冲突
        
        根据配置的 overlap_mode 判断冲突方式：
        - partial: 有重叠即过滤（活动与没时间段有任何交集）
        - full: 完全包含才过滤（活动时间必须完全被没时间段包含）
        
        Args:
            activity: 活动对象
            
        Returns:
            如果冲突返回 FilteredActivity，否则返回 None
        """
        # 获取活动举办时间
        hold_time = activity.hold_time
        if hold_time is None:
            # 无法获取活动时间，保守处理：保留该活动
            logger.debug(f"活动 '{activity.name}' 无法获取举办时间，保留")
            return None

        # 获取活动开始时间，用于确定是星期几
        activity_start = hold_time.start
        if activity_start is None:
            logger.debug(f"活动 '{activity.name}' 无法获取开始时间，保留")
            return None

        # 确定是星期几（0=周一，6=周日）
        weekday = activity_start.weekday()

        # 获取该日期用户没空的时间段
        busy_ranges = self.time_config.weekly_preferences.get_day_preference(weekday)
        if not busy_ranges:
            # 该日期没有配置没空时间，保留该活动
            return None

        # 获取活动时间段的 time 对象
        act_start_time = activity_start.time()
        act_end_time = hold_time.end.time() if hold_time.end else None

        # 如果活动没有结束时间，假设活动持续2小时
        if act_end_time is None:
            act_end_time = (datetime.combine(datetime.today(), act_start_time) + timedelta(hours=2)).time()

        # 检查是否与任何没空时间段冲突
        overlap_mode = self.time_config.overlap_mode
        conflicting_ranges = []

        for busy_range in busy_ranges:
            busy_start, busy_end = busy_range.to_time_objects()

            # 根据重叠模式判断冲突
            if overlap_mode == "partial":
                # 模式1: 有重叠即过滤
                # 重叠条件：活动开始时间 < 忙碌结束时间 且 活动结束时间 > 忙碌开始时间
                if act_start_time < busy_end and act_end_time > busy_start:
                    conflicting_ranges.append(busy_range)

            elif overlap_mode == "full":
                # 模式2: 完全包含才过滤
                # 完全包含条件：忙碌开始时间 <= 活动开始时间 且 活动结束时间 <= 忙碌结束时间
                if busy_start <= act_start_time and act_end_time <= busy_end:
                    conflicting_ranges.append(busy_range)

        if conflicting_ranges:
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            day_name = day_names[weekday]

            # 格式化冲突时间段
            ranges_str = ", ".join(str(r) for r in conflicting_ranges)

            # 根据模式显示不同的过滤原因
            if overlap_mode == "partial":
                overlap_desc = "时间冲突"
            else:
                overlap_desc = "时间完全被占用"

            reason = f"与{day_name}的{overlap_desc} ({ranges_str})"

            logger.debug(f"活动 '{activity.name}' {reason}")

            return FilteredActivity(
                activity=activity,
                reason=reason,
                filter_type="time",
                extra_data={
                    "conflicting_ranges": conflicting_ranges,
                    "weekday": weekday,
                    "day_name": day_name,
                }
            )

        return None

    def get_filter_summary(self, filtered: list[FilteredActivity]) -> str:
        """
        生成被过滤活动的汇总信息
        
        Args:
            filtered: 被过滤的活动列表
            
        Returns:
            格式化的汇总文本
        """
        if not filtered:
            return ""

        lines = [f"⏰ 根据时间偏好，已过滤 {len(filtered)} 个冲突活动："]

        for i, item in enumerate(filtered, 1):
            activity = item.activity
            lines.append(f"[{i}] {activity.name}")

            # 添加活动时间信息
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
        """
        获取当前时间偏好配置的摘要
        
        Returns:
            格式化的配置摘要
        """
        if not self.is_enabled():
            return "⏰ 时间筛选：未启用"

        lines = ["⏰ 时间筛选：已启用", ""]
        lines.append("📅 您配置的不方便时间段：")
        lines.append(self.time_config.weekly_preferences.format_preferences())

        return "\n".join(lines)


def create_time_filter_from_config() -> TimeFilter:
    """
    从配置创建时间筛选器实例
    
    Returns:
        TimeFilter 实例
    """
    from src.config.preferences import load_preferences

    preferences = load_preferences()
    return TimeFilter(preferences)
