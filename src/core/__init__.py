"""核心功能模块"""

from src.models.filter_result import FilteredActivity

from .ai_filter import AIFilter, AIFilterConfig
from .auth_manager import AuthManager
from .auto_enroller import AutoEnroller
from .db_manager import DatabaseManager
from .diff_engine import DiffEngine
from .enrolled_filter import EnrolledFilter
from .filter import SecondClassFilter
from .overlay_filter import OverlayFilter
from .scanner import ActivityScanner
from .time_filter import TimeFilter
from .user_preference_manager import UserPreferenceManager

__all__ = [
    "AIFilter",
    "AIFilterConfig",
    "AuthManager",
    "AutoEnroller",
    "DatabaseManager",
    "DiffEngine",
    "EnrolledFilter",
    "OverlayFilter",
    "ActivityScanner",
    "SecondClassFilter",
    "TimeFilter",
    "UserPreferenceManager",
    "FilteredActivity",
]
