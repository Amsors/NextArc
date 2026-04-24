"""应用装配模块。"""

from .context import AppContext
from .factory import build_card_display_config, build_notification_runtime_config

__all__ = [
    "AppContext",
    "build_card_display_config",
    "build_notification_runtime_config",
]
