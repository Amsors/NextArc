"""上下文管理器。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pyustc.young import SecondClass

from src.utils.logger import get_logger

from .models import (
    ConfirmationPayload,
    ContextRecord,
    ContextType,
    DisplayedActivitiesPayload,
    SearchResultPayload,
)
from .policies import get_default_ttl
from .store import InMemoryContextStore

if TYPE_CHECKING:
    from src.models.filter_result import FilteredActivity

logger = get_logger("context.manager")


class ContextManager:
    """单实例上下文管理器。"""

    def __init__(self, store: InMemoryContextStore | None = None) -> None:
        self.store = store or InMemoryContextStore()

    async def set(self, record: ContextRecord) -> None:
        await self.store.set(record)

    def set_sync(self, record: ContextRecord) -> None:
        self.store.set_sync(record)

    async def get(self, context_type: ContextType) -> ContextRecord | None:
        return self.get_sync(context_type)

    def get_sync(self, context_type: ContextType) -> ContextRecord | None:
        record = self.store.get_sync(context_type)
        if record and record.is_expired():
            self.store.clear_sync(context_type)
            logger.debug("上下文已过期并清理: %s", context_type.value)
            return None
        return record

    async def clear(self, context_type: ContextType | None = None) -> None:
        await self.store.clear(context_type)

    def clear_sync(self, context_type: ContextType | None = None) -> None:
        self.store.clear_sync(context_type)

    async def cleanup_expired(self) -> int:
        now = datetime.now()
        expired_types = [
            context_type
            for context_type, record in self.store.items()
            if record.is_expired(now)
        ]
        for context_type in expired_types:
            await self.store.clear(context_type)
        return len(expired_types)

    async def set_search_result(
        self,
        keyword: str,
        results: list[SecondClass],
        ttl: timedelta | None = None,
    ) -> None:
        await self.set(
            self._record(
                ContextType.SEARCH_RESULT,
                SearchResultPayload(keyword=keyword, results=results),
                ttl=ttl,
                source="search",
            )
        )

    async def get_search_result(self) -> SearchResultPayload | None:
        record = await self.get(ContextType.SEARCH_RESULT)
        return record.payload if record else None

    async def get_search_activity_by_index(self, index: int) -> SecondClass | None:
        payload = await self.get_search_result()
        if not payload:
            return None
        return payload.get_result_by_index(index)

    async def set_displayed_activities(
        self,
        activities: list[SecondClass],
        *,
        filtered_activities: dict[str, list[FilteredActivity]] | None = None,
        source: str = "unknown",
        ttl: timedelta | None = None,
    ) -> None:
        await self.set(
            self._record(
                ContextType.DISPLAYED_ACTIVITIES,
                DisplayedActivitiesPayload(
                    activities=activities,
                    filtered_activities=filtered_activities,
                ),
                ttl=ttl,
                source=source,
            )
        )
        logger.debug("保存显示的活动列表: %s 个，来源: %s", len(activities), source)

    async def get_displayed_activities(self) -> DisplayedActivitiesPayload | None:
        record = await self.get(ContextType.DISPLAYED_ACTIVITIES)
        return record.payload if record else None

    async def get_all_displayed_activities(self) -> list[SecondClass]:
        payload = await self.get_displayed_activities()
        return payload.activities if payload else []

    async def get_displayed_activity_by_index(self, index: int) -> SecondClass | None:
        payload = await self.get_displayed_activities()
        if not payload:
            return None
        return payload.get_activity_by_index(index)

    async def get_filtered_activities(self) -> dict[str, list[FilteredActivity]] | None:
        payload = await self.get_displayed_activities()
        if not payload or not payload.filtered_activities:
            return None
        return payload.filtered_activities

    async def get_filtered_activities_by_type(self, filter_type: str) -> list[FilteredActivity]:
        filtered = await self.get_filtered_activities()
        if not filtered:
            return []

        type_mapping = {
            "ai": ["ai"],
            "db": ["db", "ignore"],
            "ignore": ["db", "ignore"],
            "time": ["time"],
            "overlay": ["overlay"],
        }
        valid_types = type_mapping.get(filter_type.lower(), [filter_type.lower()])

        result: list[FilteredActivity] = []
        for current_type, activities in filtered.items():
            if current_type in valid_types:
                result.extend(activities)
        return result

    async def parse_displayed_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        payload = await self.get_displayed_activities()
        if not payload:
            return [], ["没有可操作的最近活动列表"]
        return payload.parse_indices(indices_str)

    async def set_confirmation(
        self,
        operation: Literal["cancel", "join", "restart", "upgrade"],
        activity_id: str | None = None,
        activity_name: str | None = None,
        data: dict | None = None,
        ttl: timedelta | None = None,
    ) -> None:
        await self.set(
            self._record(
                ContextType.CONFIRMATION,
                ConfirmationPayload(
                    operation=operation,
                    activity_id=activity_id,
                    activity_name=activity_name,
                    data=data,
                ),
                ttl=ttl,
                source=operation,
            )
        )

    async def get_confirmation(self) -> ConfirmationPayload | None:
        record = await self.get(ContextType.CONFIRMATION)
        return record.payload if record else None

    async def clear_confirmation(self) -> None:
        await self.clear(ContextType.CONFIRMATION)

    def _record(
        self,
        context_type: ContextType,
        payload,
        *,
        ttl: timedelta | None = None,
        source: str | None = None,
    ) -> ContextRecord:
        created_at = datetime.now()
        ttl = ttl if ttl is not None else get_default_ttl(context_type)
        expires_at = created_at + ttl if ttl else None
        return ContextRecord(
            type=context_type,
            payload=payload,
            created_at=created_at,
            expires_at=expires_at,
            source=source,
        )
