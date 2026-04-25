"""通知监听器 - 订阅事件并发送通知"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.events.scan_events import (
    ScanCompletedEvent,
    NewActivitiesFoundEvent,
    EnrolledActivityChangedEvent,
)
from src.core.events.version_events import VersionUpdateEvent
from src.utils.logger import get_logger
from .builders import (
    EnrolledActivityChangeNotificationBuilder,
    FilterDetailBuildConfig,
    FilterDetailNotificationBuilder,
    NewActivitiesCardBuildConfig,
    NewActivitiesNotificationBuilder,
    VersionNotificationBuilder,
)
from .service import NotificationService

if TYPE_CHECKING:
    from src.context import ContextManager

logger = get_logger("notifications.listener")


@dataclass(frozen=True)
class NotificationRuntimeConfig:
    """通知监听器运行时配置。"""

    notify_filtered_activities: bool = True
    show_filtered_ai_reasons: bool = False
    show_kept_ai_reasons: bool = False


class NotificationDeliveryError(RuntimeError):
    """通知发送失败，可被 EventBus 聚合到发布结果中。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class NotificationListener:
    """订阅 EventBus 事件，通过 NotificationService 发送通知"""

    def __init__(
        self,
        notification_service: NotificationService,
        user_preference_manager=None,
        context_manager: "ContextManager | None" = None,
        runtime_config: NotificationRuntimeConfig | None = None,
        filter_detail_builder: FilterDetailNotificationBuilder | None = None,
        new_activities_builder: NewActivitiesNotificationBuilder | None = None,
        enrolled_change_builder: EnrolledActivityChangeNotificationBuilder | None = None,
        version_builder: VersionNotificationBuilder | None = None,
    ):
        self._notification_service = notification_service
        self._context_manager = context_manager
        self._user_preference_manager = user_preference_manager
        self._runtime_config = runtime_config or NotificationRuntimeConfig()
        self._filter_detail_builder = filter_detail_builder or FilterDetailNotificationBuilder()
        self._new_activities_builder = new_activities_builder or NewActivitiesNotificationBuilder()
        self._enrolled_change_builder = enrolled_change_builder or EnrolledActivityChangeNotificationBuilder()
        self._version_builder = version_builder or VersionNotificationBuilder()

    async def on_scan_completed(self, event: ScanCompletedEvent) -> None:
        logger.debug(f"收到扫描完成事件: {event.new_db_path.name}")

    async def on_new_activities_found(self, event: NewActivitiesFoundEvent) -> None:
        logger.info(f"收到新活动事件: {event.final_count} 个活动")

        logger.debug(f"新活动事件 ai_keep_reasons: {event.ai_keep_reasons}")

        send_errors: list[str] = []
        notify_filtered_activities = self._runtime_config.notify_filtered_activities
        include_filtered_ai_reasons = self._runtime_config.show_filtered_ai_reasons
        include_kept_ai_reasons = self._runtime_config.show_kept_ai_reasons
        logger.info(
            "新活动通知配置: filtered=%s, kept=%s, notify_filtered_activities=%s",
            include_filtered_ai_reasons,
            include_kept_ai_reasons,
            notify_filtered_activities,
        )

        filter_message = self._filter_detail_builder.build(
            event,
            FilterDetailBuildConfig(
                enabled=notify_filtered_activities,
                include_ai_reasons=include_filtered_ai_reasons,
            ),
        )
        if filter_message:
            try:
                success = await self._notification_service.send_text(filter_message)
                if not success:
                    send_errors.append("发送筛选详情失败")
            except Exception as e:
                logger.error(f"发送筛选详情异常: {e}")
                send_errors.append(f"发送筛选详情异常: {e}")

        if event.activities:
            try:
                ignored_ids = set()
                if self._user_preference_manager:
                    try:
                        ignored_ids = await self._user_preference_manager.get_all_ignored_ids()
                    except Exception as e:
                        logger.warning(f"获取忽略列表失败: {e}")

                card_request = self._new_activities_builder.build(
                    event,
                    ignored_ids=ignored_ids,
                    config=NewActivitiesCardBuildConfig(
                        include_ai_reasons=include_kept_ai_reasons,
                        include_overlap_reasons=bool(event.overlap_reasons),
                    ),
                )
                success = True
                if card_request is not None:
                    success = await self._notification_service.send_activity_list_card(card_request)
                if success:
                    logger.info(f"已发送新活动卡片: {event.final_count} 个活动")
                else:
                    send_errors.append("发送新活动卡片失败")
            except Exception as e:
                logger.error(f"发送新活动卡片失败: {e}")
                send_errors.append(f"发送新活动卡片异常: {e}")

        else:
            logger.debug("没有新活动需要通知，仅发送过滤详情")

        if self._context_manager and (event.activities or any(event.filters_applied.values())):
            try:
                await self._context_manager.set_displayed_activities(
                    activities=event.activities,
                    filtered_activities=event.filters_applied,
                    source="new_activities"
                )
                filtered_count = sum(len(items) for items in event.filters_applied.values())
                logger.debug(
                    "已更新 ContextManager，保存了 %s 个新活动和 %s 个被筛选活动",
                    len(event.activities),
                    filtered_count,
                )
            except Exception as e:
                logger.error(f"更新 ContextManager 失败: {e}")

        if send_errors:
            raise NotificationDeliveryError(send_errors)

    async def on_enrolled_activity_changed(self, event: EnrolledActivityChangedEvent) -> None:
        if not event.changes:
            return

        logger.info(f"收到已报名活动变更事件: {event.change_count} 处变更")

        message = self._enrolled_change_builder.build(event)
        try:
            success = await self._notification_service.send_text(message)
            if success:
                logger.info(f"已发送已报名活动变更通知: {event.change_count} 个活动")
                return
            raise NotificationDeliveryError(["发送已报名活动变更通知失败"])
        except Exception as e:
            logger.error(f"发送已报名活动变更通知失败: {e}")
            if isinstance(e, NotificationDeliveryError):
                raise
            raise NotificationDeliveryError([f"发送已报名活动变更通知异常: {e}"]) from e

    async def on_version_update(self, event: VersionUpdateEvent) -> None:
        if not event.new_commits:
            return

        logger.info(f"收到版本更新事件: 落后 {event.commits_behind} 个 commit")

        message = self._version_builder.build(event)
        if not message:
            return

        try:
            success = await self._notification_service.send_text(message)
            if success:
                logger.info("已发送版本更新通知")
            else:
                raise NotificationDeliveryError(["发送版本更新通知失败"])
        except Exception as e:
            logger.error(f"发送版本更新通知失败: {e}")
            if isinstance(e, NotificationDeliveryError):
                raise
            raise NotificationDeliveryError([f"发送版本更新通知异常: {e}"]) from e

    def subscribe(self, event_bus) -> None:
        event_bus.subscribe(ScanCompletedEvent, self.on_scan_completed)
        event_bus.subscribe(NewActivitiesFoundEvent, self.on_new_activities_found)
        event_bus.subscribe(EnrolledActivityChangedEvent, self.on_enrolled_activity_changed)
        event_bus.subscribe(VersionUpdateEvent, self.on_version_update)
        logger.info("通知监听器已订阅所有事件")
