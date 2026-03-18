from src.models import Activity, SecondClassStatus
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any, Set

from src.utils.logger import get_logger

logger = get_logger("filter")

@dataclass
class SecondClassFilter:
    # 基础条件（所有条件默认None表示不限制）
    name_contains: Optional[str] = None
    excluded_status: Optional[list[SecondClassStatus]] = None

    # 高级：自定义谓词函数
    custom_predicate: Optional[Callable[[Activity], bool]] = None

    # 逻辑组合（用于复杂查询）
    _and_filters: List['SecondClassFilter'] = field(default_factory=list)
    _or_filters: List['SecondClassFilter'] = field(default_factory=list)
    _not_filter: Optional['SecondClassFilter'] = None

    # ==================== 链式构建方法 ====================

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

    # ==================== 执行方法 ====================

    def apply(self, activities: List[Activity]) -> List[Activity]:
        """执行筛选"""
        return [c for c in activities if self._matches(c)]

    def _matches(self, activity: Activity) -> bool:
        """检查单个活动是否匹配"""

        # 检查基础条件
        if self.name_contains and self.name_contains not in activity.name:
            return False

        if self.excluded_status:
            logger.debug(f"检查活动状态 {activity.status} 是否在排除列表中")
            try:
                status_obj = SecondClassStatus.from_code(activity.status)
                if status_obj is None:
                    logger.warning(f"活动状态 {activity.status} 未找到对应的枚举成员")
                    return True
                if status_obj in self.excluded_status:
                    return False
            except Exception as e:
                logger.error(f"检查活动状态时出错: {e}, 状态码={activity.status}")
                return True  # 出错时默认包含

        # 逻辑组合条件

        # AND: 所有附加条件必须满足
        for f in self._and_filters:
            if not f._matches(activity):
                return False

        # OR: 至少一个附加条件满足（如果没有OR条件则跳过）
        if self._or_filters:
            if not any(f._matches(activity) for f in self._or_filters):
                return False

        # NOT: 取反
        if self._not_filter and self._not_filter._matches(activity):
            return False

        return True

    def __call__(self, sc: List[Activity]) -> List[Activity]:
        """使筛选器可调用"""
        return self.apply(sc)