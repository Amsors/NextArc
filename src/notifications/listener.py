"""通知监听器 - 订阅事件并发送通知"""

from typing import TYPE_CHECKING

from src.core.events.scan_events import (
    ScanCompletedEvent,
    NewActivitiesFoundEvent,
    EnrolledActivityChangedEvent,
)
from src.utils.formatter import format_db_filtered_result, \
    format_ai_filtered_result, format_time_filtered_result, format_enrolled_filtered_result
from src.utils.logger import get_logger
from .service import NotificationService

if TYPE_CHECKING:
    from src.models import UserSession

logger = get_logger("notifications.listener")


class NotificationListener:
    """订阅 EventBus 事件，通过 NotificationService 发送通知"""

    def __init__(self, notification_service: NotificationService, user_preference_manager=None):
        self._notification_service = notification_service
        self._user_session: "UserSession | None" = None
        self._user_preference_manager = user_preference_manager

    def set_user_session(self, session: "UserSession") -> None:
        """设置用户会话引用（单用户场景）"""
        self._user_session = session
        logger.debug("已设置 UserSession 引用")

    async def on_scan_completed(self, event: ScanCompletedEvent) -> None:
        """处理扫描完成事件（通常不需要发送通知）"""
        logger.debug(f"收到扫描完成事件: {event.new_db_path.name}")

    async def on_new_activities_found(self, event: NewActivitiesFoundEvent) -> None:
        """处理发现新活动事件，发送筛选信息和活动卡片"""
        if not event.activities:
            logger.debug("没有新活动需要通知")
            return

        logger.info(f"收到新活动事件: {event.final_count} 个活动")

        # 构建筛选信息消息
        message_parts = []

        if event.enrolled_filtered_count > 0:
            message_parts.append(format_enrolled_filtered_result(event.filters_applied.get("enrolled", [])))

        if event.db_filtered_count > 0:
            message_parts.append(format_db_filtered_result(event.filters_applied.get("db", [])))

        if event.ai_filtered_count > 0:
            message_parts.append(format_ai_filtered_result(event.filters_applied.get("ai", [])))

        if event.time_filtered_count > 0:
            message_parts.append(format_time_filtered_result(event.filters_applied.get("time", [])))

        if message_parts:
            filter_message = "\n".join(message_parts)
            await self._notification_service.send_text(filter_message)

        # 发送活动卡片
        try:
            ignored_ids = set()
            if self._user_preference_manager:
                try:
                    ignored_ids = await self._user_preference_manager.get_all_ignored_ids()
                except Exception as e:
                    logger.warning(f"获取忽略列表失败: {e}")

            await self._notification_service.send_activity_list_card(
                event.activities,
                f"有 {event.final_count} 个你可能感兴趣的活动",
                ignored_ids=ignored_ids
            )
            logger.info(f"已发送新活动卡片: {event.final_count} 个活动")
        except Exception as e:
            logger.error(f"发送新活动卡片失败: {e}")

        # 更新 UserSession，使用户可以通过 /ignore 忽略这些活动
        if self._user_session:
            try:
                self._user_session.set_displayed_activities(
                    activities=event.activities,
                    filtered_activities=event.filters_applied,
                    source="new_activities"
                )
                logger.debug(f"已更新 UserSession，保存了 {len(event.activities)} 个新活动")
            except Exception as e:
                logger.error(f"更新 UserSession 失败: {e}")

    async def on_enrolled_activity_changed(self, event: EnrolledActivityChangedEvent) -> None:
        """处理已报名活动变更事件"""
        if not event.changes:
            return

        logger.info(f"收到已报名活动变更事件: {event.change_count} 处变更")

        for change in event.changes:
            message = (
                f"已报名活动有更新\n\n"
                f"{change.activity_name}\n"
                f"{change.format(1)}"
            )
            try:
                await self._notification_service.send_text(message)
                logger.info(f"已发送变更通知: {change.activity_name}")
            except Exception as e:
                logger.error(f"发送变更通知失败: {e}")

    def subscribe(self, event_bus) -> None:
        """订阅事件到 EventBus"""
        event_bus.subscribe(ScanCompletedEvent, self.on_scan_completed)
        event_bus.subscribe(NewActivitiesFoundEvent, self.on_new_activities_found)
        event_bus.subscribe(EnrolledActivityChangedEvent, self.on_enrolled_activity_changed)
        logger.info("通知监听器已订阅所有事件")
