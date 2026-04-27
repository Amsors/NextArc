"""事件总线实现"""

import asyncio
from dataclasses import dataclass
from collections.abc import Callable, Awaitable
from typing import Any, TypeVar, Type

from src.utils.logger import get_logger

logger = get_logger("event_bus")

from .scan_events import (
    ScanCompletedEvent,
    NewActivitiesFoundEvent,
    EnrolledActivityChangedEvent,
    ActivityIgnoredEvent,
)
from .version_events import (
    VersionUpdateEvent,
    CommitInfo,
)

__all__ = [
    "EventBus",
    "EventPublishResult",
    "ListenerResult",
    "ScanCompletedEvent",
    "NewActivitiesFoundEvent",
    "EnrolledActivityChangedEvent",
    "ActivityIgnoredEvent",
    "VersionUpdateEvent",
    "CommitInfo",
]

T = TypeVar("T")


@dataclass
class ListenerResult:
    """单个事件监听器执行结果。"""

    listener_name: str
    success: bool
    error: str | None = None


@dataclass
class EventPublishResult:
    """一次事件发布的监听器聚合结果。"""

    event_type: str
    listener_results: list[ListenerResult]

    @property
    def success(self) -> bool:
        return all(result.success for result in self.listener_results)

    @property
    def error_messages(self) -> list[str]:
        return [
            f"{result.listener_name}: {result.error}"
            for result in self.listener_results
            if not result.success and result.error
        ]


class EventBus:
    def __init__(self):
        self._listeners: dict[Type, list[Callable[[Any], Awaitable[Any]]]] = {}

    def subscribe(self, event_type: Type[T], listener: Callable[[T], Awaitable[Any]]) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)
        logger.debug(f"已订阅事件 {event_type.__name__}，当前监听器数: {len(self._listeners[event_type])}")

    def unsubscribe(self, event_type: Type[T], listener: Callable[[T], Awaitable[None]]) -> bool:
        if event_type not in self._listeners:
            return False

        try:
            self._listeners[event_type].remove(listener)
            logger.debug(f"已取消订阅事件 {event_type.__name__}")
            return True
        except ValueError:
            return False

    async def publish(self, event: T) -> EventPublishResult:
        event_type = type(event)
        listeners = self._listeners.get(event_type, [])

        if not listeners:
            logger.debug(f"事件 {event_type.__name__} 无监听器")
            return EventPublishResult(event_type=event_type.__name__, listener_results=[])

        logger.debug(f"发布事件 {event_type.__name__} 到 {len(listeners)} 个监听器")

        tasks = []
        results: list[ListenerResult] = []
        for listener in listeners:
            try:
                task = asyncio.create_task(self._invoke_listener(listener, event, event_type))
                tasks.append(task)
            except Exception as e:
                logger.error(f"创建监听器任务失败: {e}")
                results.append(
                    ListenerResult(
                        listener_name=self._get_listener_name(listener),
                        success=False,
                        error=str(e),
                    )
                )

        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for item in gathered:
                if isinstance(item, ListenerResult):
                    results.append(item)
                elif isinstance(item, Exception):
                    results.append(
                        ListenerResult(
                            listener_name="unknown",
                            success=False,
                            error=str(item),
                        )
                    )

        return EventPublishResult(event_type=event_type.__name__, listener_results=results)

    async def _invoke_listener(self, listener: Callable, event: Any, event_type: Type) -> ListenerResult:
        listener_name = self._get_listener_name(listener)
        try:
            await listener(event)
            return ListenerResult(listener_name=listener_name, success=True)
        except Exception as e:
            logger.error(f"事件监听器处理 {event_type.__name__} 失败: {e}", exc_info=True)
            return ListenerResult(listener_name=listener_name, success=False, error=str(e))

    @staticmethod
    def _get_listener_name(listener: Callable) -> str:
        if hasattr(listener, "__self__") and getattr(listener, "__self__", None):
            owner = listener.__self__.__class__.__name__
            name = getattr(listener, "__name__", repr(listener))
            return f"{owner}.{name}"
        return getattr(listener, "__qualname__", getattr(listener, "__name__", repr(listener)))

    def clear(self) -> None:
        self._listeners.clear()
        logger.debug("已清除所有事件监听器")

    def get_listener_count(self, event_type: Type | None = None) -> int:
        if event_type:
            return len(self._listeners.get(event_type, []))
        return sum(len(listeners) for listeners in self._listeners.values())
