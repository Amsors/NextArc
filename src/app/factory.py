"""应用上下文辅助构造函数。"""

from src.config.settings import Settings
from src.notifications.listener import NotificationRuntimeConfig
from src.notifications.service import CardDisplayConfig


def build_card_display_config(settings: Settings) -> CardDisplayConfig:
    """从主配置提取卡片展示配置。"""

    return CardDisplayConfig(max_activities_per_card=settings.feishu.max_activities_per_card)


def build_notification_runtime_config(settings: Settings) -> NotificationRuntimeConfig:
    """从主配置提取通知监听器运行时配置。"""

    return NotificationRuntimeConfig(
        notify_filtered_activities=settings.monitor.notify_filtered_activities,
        show_filtered_ai_reasons=settings.feishu.send_ai_filter_detail.filtered,
        show_kept_ai_reasons=settings.feishu.send_ai_filter_detail.kept,
    )
