"""通知监听器 - 订阅事件并发送通知"""

from src.core.events.scan_events import (
    ScanCompletedEvent,
    NewActivitiesFoundEvent,
    EnrolledActivityChangedEvent,
)
from src.utils.formatter import build_activity_card, format_db_filtered_result, \
    format_ai_filtered_result, format_time_filtered_result
from src.utils.logger import get_logger

from .service import NotificationService

logger = get_logger("notifications.listener")


class NotificationListener:
    """
    通知监听器

    订阅 EventBus 的事件，并通过 NotificationService 发送通知。
    实现通知逻辑与业务逻辑的解耦。
    """

    def __init__(self, notification_service: NotificationService):
        self._notification_service = notification_service

    async def on_scan_completed(self, event: ScanCompletedEvent) -> None:
        """
        处理扫描完成事件

        Args:
            event: 扫描完成事件
        """
        logger.debug(f"收到扫描完成事件: {event.new_db_path.name}")
        # 扫描完成事件通常不需要发送通知，除非有错误
        # 通知逻辑已在其他事件中处理

    async def on_new_activities_found(self, event: NewActivitiesFoundEvent) -> None:
        """
        处理发现新活动事件

        Args:
            event: 新活动发现事件
        """
        if not event.activities:
            logger.debug("没有新活动需要通知")
            return

        logger.info(f"收到新活动事件: {event.final_count} 个活动")

        # 构建筛选信息消息
        message_parts = []

        # 数据库筛选信息
        if event.db_filtered_count > 0:
            # message_parts.append(f"🗑️ 数据库筛选已过滤 {event.db_filtered_count} 个不感兴趣的活动\n")
            message_parts.append(format_db_filtered_result(event.filters_applied.get("db", [])))

        # AI 筛选信息
        if event.ai_filtered_count > 0:
            # message_parts.append(f"🤖 AI 过滤了 {event.ai_filtered_count} 个可能不感兴趣的活动\n")
            message_parts.append(format_ai_filtered_result(event.filters_applied.get("ai", [])))

        # 时间筛选信息
        if event.time_filtered_count > 0:
            # message_parts.append(f"⏰ 时间筛选过滤了 {event.time_filtered_count} 个活动\n")
            message_parts.append(format_time_filtered_result(event.filters_applied.get("time", [])))

        # 发送筛选信息
        if message_parts:
            filter_message = "\n".join(message_parts)
            await self._notification_service.send_text(filter_message)

        # 发送活动卡片
        try:
            card_content = build_activity_card(
                event.activities,
                f"🆕 发现 {event.final_count} 个新活动"
            )
            await self._notification_service.send_card(card_content)
            logger.info(f"已发送新活动卡片: {event.final_count} 个活动")
        except Exception as e:
            logger.error(f"发送新活动卡片失败: {e}")

    async def on_enrolled_activity_changed(self, event: EnrolledActivityChangedEvent) -> None:
        """
        处理已报名活动变更事件

        Args:
            event: 已报名活动变更事件
        """
        if not event.changes:
            return

        logger.info(f"收到已报名活动变更事件: {event.change_count} 处变更")

        for change in event.changes:
            message = (
                f"🔔 已报名活动有更新\n\n"
                f"📝 {change.activity_name}\n"
                f"{change.format(1)}"
            )
            try:
                await self._notification_service.send_text(message)
                logger.info(f"已发送变更通知: {change.activity_name}")
            except Exception as e:
                logger.error(f"发送变更通知失败: {e}")

    def subscribe(self, event_bus) -> None:
        """
        订阅事件到 EventBus

        Args:
            event_bus: 事件总线实例
        """
        event_bus.subscribe(ScanCompletedEvent, self.on_scan_completed)
        event_bus.subscribe(NewActivitiesFoundEvent, self.on_new_activities_found)
        event_bus.subscribe(EnrolledActivityChangedEvent, self.on_enrolled_activity_changed)
        logger.info("通知监听器已订阅所有事件")
