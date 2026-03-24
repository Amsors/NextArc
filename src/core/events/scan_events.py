"""扫描相关事件定义"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyustc.young import SecondClass

from src.models.diff_result import DiffResult, ActivityChange


@dataclass
class ScanCompletedEvent:
    """扫描完成事件"""
    new_db_path: Path
    old_db_path: Path | None
    activity_count: int
    enrolled_count: int
    diff: DiffResult | None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class NewActivitiesFoundEvent:
    """发现新活动事件"""
    activities: list[SecondClass]  # SecondClass 对象列表
    total_found: int
    filters_applied: dict[str, list]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def db_filtered_count(self) -> int:
        """数据库筛选过滤的数量"""
        return len(self.filters_applied.get("db", []))

    @property
    def time_filtered_count(self) -> int:
        """时间筛选过滤的数量"""
        return len(self.filters_applied.get("time", []))

    @property
    def ai_filtered_count(self) -> int:
        """AI筛选过滤的数量"""
        return len(self.filters_applied.get("ai", []))

    @property
    def final_count(self) -> int:
        """最终剩余活动数量"""
        return len(self.activities)


@dataclass
class EnrolledActivityChangedEvent:
    """已报名活动变更事件"""
    changes: list[ActivityChange]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def change_count(self) -> int:
        return len(self.changes)


@dataclass
class ActivityIgnoredEvent:
    """活动被忽略事件"""
    activity_id: str
    activity_name: str
    ignored_count: int  # 当前忽略列表总数
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
