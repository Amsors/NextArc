"""事件总线实现

提供轻量级的事件发布/订阅机制，用于解耦系统组件。
"""

import asyncio
from collections.abc import Callable, Awaitable
from typing import Any, TypeVar, Type

from src.utils.logger import get_logger

logger = get_logger("event_bus")

# 导出事件类型
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
    """
    轻量级异步事件总线

    用于组件间解耦通信，支持异步事件监听。

    示例:
        bus = EventBus()

        # 订阅事件
        bus.subscribe(ScanCompletedEvent, on_scan_completed)

        # 发布事件
        await bus.publish(ScanCompletedEvent(...))
    """

    def __init__(self):
        self._listeners: dict[Type, list[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(self, event_type: Type[T], listener: Callable[[T], Awaitable[None]]) -> None:
        """
        订阅特定类型的事件

        Args:
            event_type: 事件类型类
            listener: 异步监听器函数，接收事件对象作为参数
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)
        logger.debug(f"已订阅事件 {event_type.__name__}，当前监听器数: {len(self._listeners[event_type])}")

    def unsubscribe(self, event_type: Type[T], listener: Callable[[T], Awaitable[None]]) -> bool:
        """
        取消订阅事件

        Args:
            event_type: 事件类型类
            listener: 要移除的监听器函数

        Returns:
            是否成功移除
        """
        if event_type not in self._listeners:
            return False

        try:
            self._listeners[event_type].remove(listener)
            logger.debug(f"已取消订阅事件 {event_type.__name__}")
            return True
        except ValueError:
            return False

    async def publish(self, event: T) -> None:
        """
        发布事件到所有订阅者

        所有监听器并行执行，互不阻塞。

        Args:
            event: 事件对象
        """
        event_type = type(event)
        listeners = self._listeners.get(event_type, [])

        if not listeners:
            logger.debug(f"事件 {event_type.__name__} 无监听器")
            return

        logger.debug(f"发布事件 {event_type.__name__} 到 {len(listeners)} 个监听器")

        # 并行执行所有监听器
        tasks = []
        for listener in listeners:
            try:
                task = asyncio.create_task(self._invoke_listener(listener, event, event_type))
                tasks.append(task)
            except Exception as e:
                logger.error(f"创建监听器任务失败: {e}")

        if tasks:
            # 等待所有任务完成，但忽略异常（每个任务内部已处理）
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _invoke_listener(self, listener: Callable, event: Any, event_type: Type) -> None:
        """调用单个监听器并处理异常"""
        try:
            await listener(event)
        except Exception as e:
            logger.error(f"事件监听器处理 {event_type.__name__} 失败: {e}", exc_info=True)

    def clear(self) -> None:
        """清除所有监听器"""
        self._listeners.clear()
        logger.debug("已清除所有事件监听器")

    def get_listener_count(self, event_type: Type | None = None) -> int:
        """
        获取监听器数量

        Args:
            event_type: 指定事件类型，None 则返回所有监听器总数
        """
        if event_type:
            return len(self._listeners.get(event_type, []))
        return sum(len(listeners) for listeners in self._listeners.values())
