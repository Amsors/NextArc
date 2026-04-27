"""通知内容构建器。"""

from dataclasses import dataclass, field

from src.core.events.scan_events import EnrolledActivityChangedEvent, NewActivitiesFoundEvent
from src.core.events.version_events import VersionUpdateEvent
from src.feishu_bot.card_builder import ActivityListCardRequest, CardButtonConfig
from src.utils.formatter import (
    format_ai_filtered_result,
    format_db_filtered_result,
    format_enrolled_filtered_result,
    format_overlay_filtered_result,
    format_time_filtered_result,
)


@dataclass(frozen=True)
class FilterDetailBuildConfig:
    """筛选详情通知构建配置。"""

    enabled: bool = True
    include_ai_reasons: bool = False


@dataclass(frozen=True)
class NewActivitiesCardBuildConfig:
    """新活动卡片构建配置。"""

    include_ai_reasons: bool = False
    include_overlap_reasons: bool = True
    button_config: CardButtonConfig = field(
        default_factory=lambda: CardButtonConfig(
            show_ignore_button=True,
            show_interested_button=True,
            show_join_button=True,
            show_children_button=True,
        )
    )


class FilterDetailNotificationBuilder:
    """构建被筛选活动详情文本。"""

    def build(
        self,
        event: NewActivitiesFoundEvent,
        config: FilterDetailBuildConfig,
    ) -> str | None:
        """根据事件和显式配置构建筛选详情文本。"""

        if not config.enabled:
            return None

        message_parts = []

        if event.enrolled_filtered_count > 0:
            message_parts.append(format_enrolled_filtered_result(event.filters_applied.get("enrolled", [])))

        if event.db_filtered_count > 0:
            message_parts.append(format_db_filtered_result(event.filters_applied.get("db", [])))

        if event.ai_filtered_count > 0:
            message_parts.append(
                format_ai_filtered_result(
                    event.filters_applied.get("ai", []),
                    include_reasons=config.include_ai_reasons,
                )
            )

        if event.time_filtered_count > 0:
            message_parts.append(format_time_filtered_result(event.filters_applied.get("time", [])))

        if event.overlay_filtered_count > 0:
            message_parts.append(format_overlay_filtered_result(event.filters_applied.get("overlay", [])))

        if not message_parts:
            return None
        return "\n".join(message_parts)


class NewActivitiesNotificationBuilder:
    """构建新活动通知卡片请求。"""

    def build(
        self,
        event: NewActivitiesFoundEvent,
        ignored_ids: set[str] | None,
        config: NewActivitiesCardBuildConfig,
    ) -> ActivityListCardRequest | None:
        """根据事件和显式配置构建活动卡片请求。"""

        if not event.activities:
            return None

        return ActivityListCardRequest(
            activities=event.activities,
            title=f"有 {event.final_count} 个你可能感兴趣的活动",
            ignored_ids=ignored_ids or set(),
            button_config=config.button_config,
            ai_reasons=event.ai_keep_reasons if config.include_ai_reasons else {},
            overlap_reasons=event.overlap_reasons if config.include_overlap_reasons else {},
        )


class EnrolledActivityChangeNotificationBuilder:
    """构建已报名活动变更通知。"""

    def build(self, event: EnrolledActivityChangedEvent) -> str:
        """将已报名活动变更事件转换为单条文本消息。"""

        lines = [f"已报名活动有更新（共 {event.change_count} 个）", ""]
        for index, change in enumerate(event.changes, 1):
            if index > 1:
                lines.append("")
            lines.append(change.format(index))
        return "\n".join(lines)


class VersionNotificationBuilder:
    """构建版本更新通知。"""

    def build(self, event: VersionUpdateEvent) -> str | None:
        """将版本更新事件转换为文本消息。"""

        if not event.new_commits:
            return None

        lines = [
            "NextArc 有新版本更新",
            "",
            f"当前版本: `{event.current_sha[:7]}`",
            f"最新版本: `{event.latest_sha[:7]}`",
            f"共 {event.commits_behind} 个新提交：",
            "",
        ]

        for i, commit in enumerate(event.new_commits[:5], 1):
            message_first_line = commit.message.split("\n")[0][:50]
            lines.append(f"{i}. {message_first_line} {commit.date}")
            lines.append("")

        if len(event.new_commits) > 5:
            lines.append(f"... 还有 {len(event.new_commits) - 5} 个提交")
            lines.append("")

        lines.append("向机器人发送 /upgrade 或 升级 即可进行更新")
        return "\n".join(lines)
