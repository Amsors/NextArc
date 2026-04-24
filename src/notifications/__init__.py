"""通知模块

提供统一的通知服务抽象和多种实现。
"""

from .builders import (
    EnrolledActivityChangeNotificationBuilder,
    FilterDetailBuildConfig,
    FilterDetailNotificationBuilder,
    NewActivitiesCardBuildConfig,
    NewActivitiesNotificationBuilder,
    VersionNotificationBuilder,
)
from .feishu_service import FeishuNotificationService
from .listener import NotificationDeliveryError, NotificationListener, NotificationRuntimeConfig
from .response import Response, ResponseType
from .service import CardDisplayConfig, NotificationService

__all__ = [
    "Response",
    "ResponseType",
    "CardDisplayConfig",
    "NotificationService",
    "FeishuNotificationService",
    "NotificationListener",
    "NotificationRuntimeConfig",
    "NotificationDeliveryError",
    "FilterDetailBuildConfig",
    "FilterDetailNotificationBuilder",
    "NewActivitiesCardBuildConfig",
    "NewActivitiesNotificationBuilder",
    "EnrolledActivityChangeNotificationBuilder",
    "VersionNotificationBuilder",
]
