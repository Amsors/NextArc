"""核心功能模块"""

from src.models.filter_result import FilteredActivity

from .ai_filter import AIFilter, AIFilterConfig
from .auth_manager import AuthManager
from .db_manager import DatabaseManager
from .diff_engine import DiffEngine
from .enrolled_filter import EnrolledFilter
from .filter import SecondClassFilter
from .filtering import ActivityFilterPipeline, FilterContext, FilterPipelineResult
from .overlay_filter import OverlayFilter
from .repositories import ActivityRepository, PreferenceKind, PreferenceRepository
from .scanner import ActivityScanner
from .services import ActivityQueryService, ActivityUpdateService, EnrollmentService
from .time_filter import TimeFilter
from .user_preference_manager import UserPreferenceManager

__all__ = [
    "AIFilter",
    "AIFilterConfig",
    "AuthManager",
    "DatabaseManager",
    "DiffEngine",
    "EnrolledFilter",
    "OverlayFilter",
    "ActivityRepository",
    "PreferenceKind",
    "PreferenceRepository",
    "ActivityScanner",
    "ActivityQueryService",
    "ActivityUpdateService",
    "EnrollmentService",
    "SecondClassFilter",
    "TimeFilter",
    "UserPreferenceManager",
    "FilteredActivity",
    "ActivityFilterPipeline",
    "FilterContext",
    "FilterPipelineResult",
]
