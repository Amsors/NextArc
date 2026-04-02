"""扫描相关事件定义"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyustc.young import SecondClass

from src.models.diff_result import DiffResult, ActivityChange


@dataclass
class ScanCompletedEvent:
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
    activities: list[SecondClass]
    total_found: int
    filters_applied: dict[str, list]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def db_filtered_count(self) -> int:
        return len(self.filters_applied.get("db", []))

    @property
    def time_filtered_count(self) -> int:
        return len(self.filters_applied.get("time", []))

    @property
    def ai_filtered_count(self) -> int:
        return len(self.filters_applied.get("ai", []))

    @property
    def enrolled_filtered_count(self) -> int:
        return len(self.filters_applied.get("enrolled", []))

    @property
    def final_count(self) -> int:
        return len(self.activities)


@dataclass
class EnrolledActivityChangedEvent:
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
    activity_id: str
    activity_name: str
    ignored_count: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
