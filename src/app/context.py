"""应用运行时依赖上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.preferences import PushPreferences
from src.config.settings import Settings
from src.context import ContextManager
from src.core import (
    ActivityFilterPipeline,
    ActivityQueryService,
    ActivityRepository,
    ActivityScanner,
    ActivityUpdateService,
    AuthManager,
    DatabaseManager,
    EnrollmentService,
    RuntimeMaintenanceService,
    UserPreferenceManager,
)
from src.core.events import EventBus
from src.core.time_filter import TimeFilter


@dataclass
class AppContext:
    """集中保存单实例应用的运行时依赖。"""

    settings: Settings
    preferences: PushPreferences
    event_bus: EventBus
    auth_manager: AuthManager
    db_manager: DatabaseManager
    activity_repo: ActivityRepository
    preference_manager: UserPreferenceManager
    context_manager: ContextManager
    activity_query_service: ActivityQueryService
    activity_update_service: ActivityUpdateService
    enrollment_service: EnrollmentService
    filter_pipeline: ActivityFilterPipeline
    scanner: ActivityScanner
    maintenance_service: RuntimeMaintenanceService | None = None
    time_filter: TimeFilter | None = None
    version_checker: Any | None = None
