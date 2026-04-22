"""上下文数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

from pyustc.young import SecondClass

if TYPE_CHECKING:
    from src.models.filter_result import FilteredActivity

T = TypeVar("T")


class ContextType(str, Enum):
    DISPLAYED_ACTIVITIES = "displayed_activities"
    SEARCH_RESULT = "search_result"
    CONFIRMATION = "confirmation"
    PREFERENCE_VIEW = "preference_view"
    CONVERSATION_STATE = "conversation_state"


@dataclass
class ContextRecord(Generic[T]):
    type: ContextType
    payload: T
    created_at: datetime
    expires_at: datetime | None = None
    source: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or datetime.now()) >= self.expires_at


@dataclass
class SearchResultPayload:
    keyword: str
    results: list[SecondClass]

    def get_result_by_index(self, index: int) -> SecondClass | None:
        if index < 1 or index > len(self.results):
            return None
        return self.results[index - 1]


@dataclass
class DisplayedActivitiesPayload:
    activities: list[SecondClass]
    filtered_activities: dict[str, list[FilteredActivity]] | None = None

    def get_activity_by_index(self, index: int) -> SecondClass | None:
        if index < 1 or index > len(self.activities):
            return None
        return self.activities[index - 1]

    def parse_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        indices_str = indices_str.strip()

        if indices_str in ["全部", "所有"]:
            return list(range(1, len(self.activities) + 1)), []

        indices: list[int] = []
        errors: list[str] = []
        parts = indices_str.split(",")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if "-" in part:
                range_parts = part.split("-", 1)
                try:
                    start = int(range_parts[0].strip())
                    end = int(range_parts[1].strip())

                    if start > end:
                        start, end = end, start

                    if start < 1 or end > len(self.activities):
                        errors.append(f"范围 {part} 超出有效范围（1-{len(self.activities)}）")
                        continue

                    indices.extend(range(start, end + 1))

                except ValueError:
                    errors.append(f"无法解析范围: {part}")
                    continue
            else:
                try:
                    idx = int(part)
                    if idx < 1 or idx > len(self.activities):
                        errors.append(f"序号 {idx} 超出有效范围（1-{len(self.activities)}）")
                        continue
                    indices.append(idx)
                except ValueError:
                    errors.append(f"无法解析序号: {part}")
                    continue

        seen: set[int] = set()
        unique_indices: list[int] = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        return unique_indices, errors


@dataclass
class ConfirmationPayload:
    operation: Literal["cancel", "join", "upgrade"]
    activity_id: str | None = None
    activity_name: str | None = None
    data: dict | None = None

    def get_confirm_prompt(self) -> str:
        if self.operation == "upgrade":
            return "请回复「确认」或「取消」"
        action = "取消报名" if self.operation == "cancel" else "报名"
        activity_name = self.activity_name or "未知活动"
        return (
            f"确定要{action}「{activity_name}」吗？\n\n"
            f"回复「确认」执行操作\n"
            f"回复「取消」放弃操作"
        )
