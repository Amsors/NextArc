"""定时扫描器兼容入口。"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pyustc.young import SecondClass

from src.core.filtering import ActivityFilterPipeline
from src.core.repositories import ActivityRepository
from src.core.scanning import (
    ActivitySyncService,
    ScanCoordinator,
    ScanDiffService,
    ScanOptions,
    VersionScheduler,
)
from src.core.services import ActivityUpdateService
from src.utils.logger import get_logger

from .ai_filter import AIFilter
from .auth_manager import AuthManager
from .db_manager import DatabaseManager
from .time_filter import TimeFilter
from .user_preference_manager import UserPreferenceManager

if TYPE_CHECKING:
    from src.core.events import EventBus

logger = get_logger("scanner")


class ActivityScanner:
    """负责定时任务生命周期，并保留旧 scanner.scan 调用入口。"""

    def __init__(
            self,
            auth_manager: AuthManager,
            db_manager: DatabaseManager,
            event_bus: Optional["EventBus"] = None,
            interval_minutes: int = 15,
            notify_new_activities: bool = True,
            ai_filter: Optional[AIFilter] = None,
            use_ai_filter: bool = False,
            ai_user_info: str = "",
            time_filter: Optional[TimeFilter] = None,
            use_time_filter: bool = False,
            user_preference_manager: Optional[UserPreferenceManager] = None,
            version_checker: Optional["VersionChecker"] = None,
            filter_pipeline: Optional[ActivityFilterPipeline] = None,
            ignore_overlap: bool = False,
            coordinator: ScanCoordinator | None = None,
            activity_update_service: ActivityUpdateService | None = None,
    ):
        self.auth_manager = auth_manager
        self.db_manager = db_manager
        self.event_bus = event_bus
        self.interval = interval_minutes
        self.notify_new_activities = notify_new_activities
        self.ai_filter = ai_filter
        self.use_ai_filter = use_ai_filter
        self.ai_user_info = ai_user_info
        self.time_filter = time_filter
        self.use_time_filter = use_time_filter
        self.user_preference_manager = user_preference_manager
        self.version_checker = version_checker
        self.ignore_overlap = ignore_overlap
        self.scheduler = AsyncIOScheduler()
        self.activity_repository = ActivityRepository()
        self.activity_update_service = activity_update_service or ActivityUpdateService(self.auth_manager)
        self.filter_pipeline = filter_pipeline or ActivityFilterPipeline(
            activity_repository=self.activity_repository,
            user_preference_manager=self.user_preference_manager,
            ai_filter=self.ai_filter,
            use_ai_filter=self.use_ai_filter,
            ai_user_info=self.ai_user_info,
            time_filter=self.time_filter,
            use_time_filter=self.use_time_filter,
        )
        self.coordinator = coordinator or ScanCoordinator(
            db_manager=self.db_manager,
            sync_service=ActivitySyncService(self.auth_manager, self.activity_repository),
            diff_service=ScanDiffService(activity_repository=self.activity_repository),
            event_bus=self.event_bus,
            filter_pipeline=self.filter_pipeline,
            activity_repository=self.activity_repository,
            activity_update_service=self.activity_update_service,
            auth_manager=self.auth_manager,
            use_ai_filter=self.use_ai_filter,
            ignore_overlap=self.ignore_overlap,
        )
        self.version_scheduler = VersionScheduler(
            scheduler=self.scheduler,
            version_checker=self.version_checker,
            event_bus=self.event_bus,
        )
        self._last_scan_time: Optional[datetime] = None
        self._is_running = False
        self._scan_lock = asyncio.Lock()

    async def scan(
            self,
            deep_update: bool,
            notify_diff: bool,
            notify_enrolled_change: bool,
            notify_new_activities: bool,
            no_filter: bool,
            wait_for_notifications: bool = False,
    ) -> dict[str, Any]:
        if self._scan_lock.locked():
            logger.warning("扫描正在进行中，跳过本次请求")
            return {
                "success": False,
                "error": "扫描正在进行中，请稍后再试",
                "new_db_path": None,
                "old_db_path": None,
                "activity_count": 0,
                "enrolled_count": 0,
                "diff": None,
                "enrolled_changes": [],
                "notification_errors": [],
            }

        async with self._scan_lock:
            scan_result = await self.coordinator.scan(
                ScanOptions(
                    deep_update=deep_update,
                    notify_diff=notify_diff,
                    notify_enrolled_change=notify_enrolled_change,
                    notify_new_activities=notify_new_activities,
                    no_filter=no_filter,
                    wait_for_notifications=wait_for_notifications,
                )
            )
            if scan_result.success:
                self._last_scan_time = datetime.now()
            return scan_result.to_dict()

    def start(self) -> None:
        if self._is_running:
            logger.warning("定时扫描已在运行")
            return

        self.scheduler.add_job(
            self.scan,
            trigger=IntervalTrigger(minutes=self.interval),
            id="activity_scan",
            replace_existing=True,
            max_instances=1,
            kwargs={
                "deep_update": True,
                "notify_diff": False,
                "notify_new_activities": True,
                "no_filter": False,
                "notify_enrolled_change": True,
            }
        )

        version_check_added = self.version_scheduler.add_job()

        self.scheduler.start()
        self._is_running = True
        logger.info(f"定时扫描已启动，间隔: {self.interval}分钟")

        if version_check_added:
            job = self.scheduler.get_job("version_check")
            if job and hasattr(job, "next_run_time") and job.next_run_time:
                logger.info(f"版本检查下次运行时间: {job.next_run_time}")

    def stop(self) -> None:
        if not self._is_running:
            return

        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("定时扫描已停止")

    def is_running(self) -> bool:
        return self._is_running

    def get_last_scan_time(self) -> Optional[datetime]:
        return self._last_scan_time

    def get_next_scan_time(self) -> Optional[datetime]:
        if not self._is_running:
            return None

        job = self.scheduler.get_job("activity_scan")
        if job and job.next_run_time:
            return job.next_run_time
        return None

    def get_next_version_check_time(self) -> Optional[datetime]:
        if not self._is_running:
            return None

        job = self.scheduler.get_job("version_check")
        if job and job.next_run_time:
            return job.next_run_time
        return None

    async def get_activity_list_by_id(
            self,
            activity_ids: list[str],
            max_concurrent: int = 5
    ) -> list[SecondClass]:
        return await self.coordinator.get_activity_list_by_id(
            activity_ids,
            max_concurrent=max_concurrent,
        )
