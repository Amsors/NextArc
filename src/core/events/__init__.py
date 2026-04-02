"""事件总线实现"""

import asyncio
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
    "ScanCompletedEvent",
    "NewActivitiesFoundEvent",
    "EnrolledActivityChangedEvent",
    "ActivityIgnoredEvent",
    "VersionUpdateEvent",
    "CommitInfo",
]

T = TypeVar("T")


class EventBus:
    def __init__(self):
        self._listeners: dict[Type, list[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(self, event_type: Type[T], listener: Callable[[T], Awaitable[None]]) -> None:
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

    async def publish(self, event: T) -> None:
        event_type = type(event)
        listeners = self._listeners.get(event_type, [])

        if not listeners:
            logger.debug(f"事件 {event_type.__name__} 无监听器")
            return

        logger.debug(f"发布事件 {event_type.__name__} 到 {len(listeners)} 个监听器")

        tasks = []
        for listener in listeners:
            try:
                task = asyncio.create_task(self._invoke_listener(listener, event, event_type))
                tasks.append(task)
            except Exception as e:
                logger.error(f"创建监听器任务失败: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _invoke_listener(self, listener: Callable, event: Any, event_type: Type) -> None:
        try:
            await listener(event)
        except Exception as e:
            logger.error(f"事件监听器处理 {event_type.__name__} 失败: {e}", exc_info=True)

    def clear(self) -> None:
        self._listeners.clear()
        logger.debug("已清除所有事件监听器")

    def get_listener_count(self, event_type: Type | None = None) -> int:
        if event_type:
            return len(self._listeners.get(event_type, []))
        return sum(len(listeners) for listeners in self._listeners.values())
