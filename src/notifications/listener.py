"""通知监听器 - 订阅事件并发送通知"""

from typing import TYPE_CHECKING

from src.core.events.scan_events import (
    ScanCompletedEvent,
    NewActivitiesFoundEvent,
    EnrolledActivityChangedEvent,
)
from src.core.events.version_events import VersionUpdateEvent
from src.utils.formatter import format_db_filtered_result, \
    format_ai_filtered_result, format_time_filtered_result, format_enrolled_filtered_result, format_overlay_filtered_result
from src.utils.logger import get_logger
from .service import NotificationService

if TYPE_CHECKING:
    from src.context import ContextManager

logger = get_logger("notifications.listener")


class NotificationListener:
    """订阅 EventBus 事件，通过 NotificationService 发送通知"""

    def __init__(self, notification_service: NotificationService, user_preference_manager=None):
        self._notification_service = notification_service
        self._context_manager: "ContextManager | None" = None
        self._user_preference_manager = user_preference_manager

    def set_context_manager(self, context_manager: "ContextManager") -> None:
        self._context_manager = context_manager
        logger.debug("已设置 ContextManager 引用")

    def set_user_session(self, session) -> None:
        self.set_context_manager(session.context_manager)

    async def on_scan_completed(self, event: ScanCompletedEvent) -> None:
        logger.debug(f"收到扫描完成事件: {event.new_db_path.name}")

    async def on_new_activities_found(self, event: NewActivitiesFoundEvent) -> None:
        logger.info(f"收到新活动事件: {event.final_count} 个活动")

        from src.config import get_settings
        settings = get_settings()
        ai_detail_config = settings.feishu.send_ai_filter_detail
        notify_filtered_activities = settings.monitor.notify_filtered_activities
        logger.info(
            f"新活动通知配置: filtered={ai_detail_config.filtered}, "
            f"kept={ai_detail_config.kept}, notify_filtered_activities={notify_filtered_activities}"
        )
        logger.debug(f"新活动事件 ai_keep_reasons: {event.ai_keep_reasons}")

        message_parts = []

        if notify_filtered_activities:
            if event.enrolled_filtered_count > 0:
                message_parts.append(format_enrolled_filtered_result(event.filters_applied.get("enrolled", [])))

            if event.db_filtered_count > 0:
                message_parts.append(format_db_filtered_result(event.filters_applied.get("db", [])))

            if event.ai_filtered_count > 0:
                message_parts.append(format_ai_filtered_result(
                    event.filters_applied.get("ai", []),
                    include_reasons=ai_detail_config.filtered,
                ))

            if event.time_filtered_count > 0:
                message_parts.append(format_time_filtered_result(event.filters_applied.get("time", [])))

            if event.overlay_filtered_count > 0:
                message_parts.append(format_overlay_filtered_result(event.filters_applied.get("overlay", [])))

        if message_parts:
            filter_message = "\n".join(message_parts)
            await self._notification_service.send_text(filter_message)

        if event.activities:
            try:
                ignored_ids = set()
                if self._user_preference_manager:
                    try:
                        ignored_ids = await self._user_preference_manager.get_all_ignored_ids()
                    except Exception as e:
                        logger.warning(f"获取忽略列表失败: {e}")

                from src.utils.formatter import CardButtonConfig
                button_config = CardButtonConfig(
                    show_ignore_button=True,
                    show_interested_button=True,
                    show_join_button=True,
                    show_children_button=True
                )

                await self._notification_service.send_activity_list_card(
                    event.activities,
                    f"有 {event.final_count} 个你可能感兴趣的活动",
                    ignored_ids=ignored_ids,
                    button_config=button_config,
                    ai_reasons=event.ai_keep_reasons if ai_detail_config.kept else None,
                    overlap_reasons=event.overlap_reasons if event.overlap_reasons else None,
                )
                logger.info(f"已发送新活动卡片: {event.final_count} 个活动")
            except Exception as e:
                logger.error(f"发送新活动卡片失败: {e}")

            if self._context_manager:
                try:
                    await self._context_manager.set_displayed_activities(
                        activities=event.activities,
                        filtered_activities=event.filters_applied,
                        source="new_activities"
                    )
                    logger.debug(f"已更新 ContextManager，保存了 {len(event.activities)} 个新活动")
                except Exception as e:
                    logger.error(f"更新 ContextManager 失败: {e}")
        else:
            logger.debug("没有新活动需要通知，仅发送过滤详情")

    async def on_enrolled_activity_changed(self, event: EnrolledActivityChangedEvent) -> None:
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

    async def on_version_update(self, event: VersionUpdateEvent) -> None:
        if not event.new_commits:
            return

        logger.info(f"收到版本更新事件: 落后 {event.commits_behind} 个 commit")

        lines = [
            "NextArc 有新版本更新",
            "",
            f"当前版本: `{event.current_sha[:7]}`",
            f"最新版本: `{event.latest_sha[:7]}`",
            f"共 {event.commits_behind} 个新提交：",
            "",
        ]

        # 只列出前 5 个 commit
        for i, commit in enumerate(event.new_commits[:5], 1):
            message_first_line = commit.message.split("\n")[0][:50]
            lines.append(f"{i}. {message_first_line} {commit.date}")
            lines.append("")

        if len(event.new_commits) > 5:
            lines.append(f"... 还有 {len(event.new_commits) - 5} 个提交")
            lines.append("")

        lines.append("向机器人发送 /upgrade 或 升级 即可进行更新")

        try:
            await self._notification_service.send_text("\n".join(lines))
            logger.info("已发送版本更新通知")
        except Exception as e:
            logger.error(f"发送版本更新通知失败: {e}")

    def subscribe(self, event_bus) -> None:
        event_bus.subscribe(ScanCompletedEvent, self.on_scan_completed)
        event_bus.subscribe(NewActivitiesFoundEvent, self.on_new_activities_found)
        event_bus.subscribe(EnrolledActivityChangedEvent, self.on_enrolled_activity_changed)
        event_bus.subscribe(VersionUpdateEvent, self.on_version_update)
        logger.info("通知监听器已订阅所有事件")
