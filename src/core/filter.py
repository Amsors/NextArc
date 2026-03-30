"""SecondClass 基础筛选器"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable

from pyustc.young import SecondClass, Status as SecondClassStatus

from src.utils.logger import get_logger

logger = get_logger("filter")


@dataclass
class SecondClassFilter:
    """SecondClass 筛选器，支持链式组合条件"""

    name_contains: Optional[str] = None
    excluded_status: Optional[list[SecondClassStatus]] = None
    custom_predicate: Optional[Callable[[SecondClass], bool]] = None

    # 逻辑组合
    _and_filters: List['SecondClassFilter'] = field(default_factory=list)
    _or_filters: List['SecondClassFilter'] = field(default_factory=list)
    _not_filter: Optional['SecondClassFilter'] = None

    def with_name(self, keyword: str) -> 'SecondClassFilter':
        """活动名包含关键词"""
        self.name_contains = keyword
        return self

    def exclude_status(self, statuses: list[SecondClassStatus]) -> 'SecondClassFilter':
        """排除指定状态"""
        self.excluded_status = statuses
        return self

    def AND(self, other: 'SecondClassFilter') -> 'SecondClassFilter':
        """与另一个筛选器组合（必须同时满足）"""
        self._and_filters.append(other)
        return self

    def OR(self, other: 'SecondClassFilter') -> 'SecondClassFilter':
        """或另一个筛选器（满足其一）"""
        self._or_filters.append(other)
        return self

    def NOT(self) -> 'SecondClassFilter':
        """取反（生成新筛选器）"""
        new_filter = SecondClassFilter()
        new_filter._not_filter = self
        return new_filter

    def apply(self, activities: List[SecondClass]) -> List[SecondClass]:
        """执行筛选"""
        return [c for c in activities if self._matches(c)]

    def _matches(self, activity: SecondClass) -> bool:
        """检查单个活动是否匹配"""
        if self.name_contains and self.name_contains not in activity.name:
            return False

        if self.excluded_status:
            try:
                if activity.status in self.excluded_status:
                    return False
            except Exception as e:
                logger.error(f"检查活动状态时出错: {e}, 状态={activity.status}")
                return True

        # AND: 所有附加条件必须满足
        for f in self._and_filters:
            if not f._matches(activity):
                return False

        # OR: 至少一个附加条件满足
        if self._or_filters:
            if not any(f._matches(activity) for f in self._or_filters):
                return False

        # NOT: 取反
        if self._not_filter and self._not_filter._matches(activity):
            return False

        return True

    def __call__(self, sc: List[SecondClass]) -> List[SecondClass]:
        """使筛选器可调用"""
        return self.apply(sc)
