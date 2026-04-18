"""用户会话数据模型"""

from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pyustc.young import SecondClass

from src.models import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("session")


class SearchSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    keyword: str
    results: list[SecondClass]
    created_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(minutes=5)

    def get_result_by_index(self, index: int) -> Optional[SecondClass]:
        if self.is_expired():
            return None
        if index < 1 or index > len(self.results):
            return None
        return self.results[index - 1]


class DisplayedActivitiesSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    activities: list[SecondClass]
    filtered_activities: dict[str, list[FilteredActivity]] | None = None
    source: str  # "valid", "new_activities", "search"
    created_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(minutes=10)

    def get_activity_by_index(self, index: int) -> Optional[SecondClass]:
        if self.is_expired():
            return None
        if index < 1 or index > len(self.activities):
            return None
        return self.activities[index - 1]

    def get_all_activities(self) -> list[SecondClass]:
        if self.is_expired():
            return []
        return self.activities

    def parse_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        """解析序号字符串，支持格式："1,2,3"、"1-5"、"1,3-5,10"、"全部" """
        indices_str = indices_str.strip()

        if indices_str in ["全部", "所有"]:
            return list(range(1, len(self.activities) + 1)), []

        indices = []
        errors = []
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

        seen = set()
        unique_indices = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        return unique_indices, errors


class ConfirmSession(BaseModel):
    operation: Literal["cancel", "join", "upgrade"]
    activity_id: Optional[str] = None
    activity_name: Optional[str] = None
    data: Optional[dict] = None  # 存储额外数据，如升级信息
    created_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(minutes=2)

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


class UserSession:
    def __init__(self) -> None:
        self.search: Optional[SearchSession] = None
        self.confirm: Optional[ConfirmSession] = None
        self.displayed_activities: Optional[DisplayedActivitiesSession] = None
        self.open_id: Optional[str] = None  # 用户的飞书 open_id，用于日历同步

    def set_search(self, keyword: str, results: list[SecondClass]) -> None:
        self.search = SearchSession(
            keyword=keyword,
            results=results,
            created_at=datetime.now()
        )

    def clear_search(self) -> None:
        self.search = None

    def set_confirm(self, operation: Literal["cancel", "join", "upgrade"],
                    activity_id: Optional[str] = None,
                    activity_name: Optional[str] = None,
                    data: Optional[dict] = None) -> None:
        self.confirm = ConfirmSession(
            operation=operation,
            activity_id=activity_id,
            activity_name=activity_name,
            data=data,
            created_at=datetime.now()
        )

    def clear_confirm(self) -> None:
        self.confirm = None

    def get_search_result(self, index: int) -> Optional[SecondClass]:
        if not self.search:
            return None
        return self.search.get_result_by_index(index)

    def set_displayed_activities(
            self,
            activities: list[SecondClass],
            filtered_activities: dict[str, list[FilteredActivity]] | None = None,
            source: str = "unknown") -> None:
        self.displayed_activities = DisplayedActivitiesSession(
            activities=activities,
            source=source,
            created_at=datetime.now(),
            filtered_activities=filtered_activities
        )
        logger.debug(f"保存显示的活动列表: {len(activities)} 个，来源: {source}")

    def clear_displayed_activities(self) -> None:
        self.displayed_activities = None

    def get_displayed_activity_by_index(self, index: int) -> Optional[SecondClass]:
        if not self.displayed_activities:
            return None
        return self.displayed_activities.get_activity_by_index(index)

    def get_all_displayed_activities(self) -> list[SecondClass]:
        if not self.displayed_activities:
            return []
        return self.displayed_activities.get_all_activities()

    def get_filtered_activities(self) -> Optional[dict[str, list[FilteredActivity]]]:
        if not self.displayed_activities.filtered_activities:
            return None
        return self.displayed_activities.filtered_activities

    def get_filtered_activities_by_type(self, filter_type: str) -> list[FilteredActivity]:
        if not self.displayed_activities:
            return []

        if self.displayed_activities.is_expired():
            return []

        filtered = self.displayed_activities.filtered_activities
        if not filtered:
            return []

        type_mapping = {
            "ai": ["ai"],
            "db": ["db", "ignore"],
            "ignore": ["db", "ignore"],
            "time": ["time"],
        }

        valid_types = type_mapping.get(filter_type.lower(), [filter_type.lower()])

        result = []
        for ft, activities in filtered.items():
            if ft in valid_types:
                result.extend(activities)

        return result

    def parse_displayed_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        if not self.displayed_activities:
            return [], ["没有可操作的最近活动列表"]
        return self.displayed_activities.parse_indices(indices_str)

    def check_confirm(self, response: str) -> Optional[tuple[str, str]]:
        """检查确认响应，返回 (operation, activity_id) 如果确认执行，None 如果取消或无效 """
        if not self.confirm or self.confirm.is_expired():
            return None

        if response == "确认":
            result = (self.confirm.operation, self.confirm.activity_id)
            self.clear_confirm()
            return result
        elif response == "取消":
            self.clear_confirm()
            return None

        return None
