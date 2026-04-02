"""筛选结果模型"""

from dataclasses import dataclass
from typing import Optional, Any

from pyustc.young import SecondClass


@dataclass
class FilteredActivity:
    activity: SecondClass
    reason: str
    filter_type: str = "unknown"
    extra_data: Optional[dict[str, Any]] = None

    def __post_init__(self):
        if not self.filter_type or self.filter_type == "unknown":
            if self.reason:
                reason_lower = self.reason.lower()
                if "ai" in reason_lower or "人工智能" in self.reason or "模型" in self.reason:
                    self.filter_type = "ai"
                elif "时间" in self.reason or "冲突" in self.reason:
                    self.filter_type = "time"
                elif "忽略" in self.reason or "不感兴趣" in self.reason or "数据库" in self.reason:
                    self.filter_type = "ignore"

    @property
    def activity_id(self) -> str:
        return self.activity.id

    @property
    def activity_name(self) -> str:
        return self.activity.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "reason": self.reason,
            "filter_type": self.filter_type,
            "extra_data": self.extra_data,
        }

    def __str__(self) -> str:
        return (f"FilteredActivity(id={self.activity_id}, "
                f"name={self.activity_name}, "
                f"reason={self.reason}, "
                f"type={self.filter_type})")

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class FilterResult:
    kept: list[SecondClass]
    filtered: list[FilteredActivity]

    def __len__(self) -> int:
        return len(self.kept) + len(self.filtered)

    @property
    def total_count(self) -> int:
        return len(self)

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    @property
    def filtered_count(self) -> int:
        return len(self.filtered)

    def get_filtered_by_type(self, filter_type: str) -> list[FilteredActivity]:
        return [f for f in self.filtered if f.filter_type == filter_type]

    def to_summary(self) -> dict[str, Any]:
        return {
            "total": self.total_count,
            "kept": self.kept_count,
            "filtered": self.filtered_count,
            "by_type": {
                "ai": len(self.get_filtered_by_type("ai")),
                "time": len(self.get_filtered_by_type("time")),
                "ignore": len(self.get_filtered_by_type("ignore")),
            }
        }
