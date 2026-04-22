"""定时扫描器"""
import asyncio
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pyustc.young import SecondClass, Status

from src.core.filtering import ActivityFilterPipeline, FilterContext
from src.core.repositories import ActivityRepository
from src.core.secondclass_db import SecondClassDB
from src.utils.logger import get_logger
from .ai_filter import AIFilter
from .auth_manager import AuthManager
from .db_manager import DatabaseManager
from .diff_engine import DiffEngine
from .time_filter import TimeFilter
from .user_preference_manager import UserPreferenceManager

if TYPE_CHECKING:
    from src.core.events import EventBus

from src.core.events.scan_events import (
    ScanCompletedEvent,
    EnrolledActivityChangedEvent,
    NewActivitiesFoundEvent,
)
from src.core.events.version_events import VersionUpdateEvent

logger = get_logger("scanner")


class ActivityScanner:
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
        self.filter_pipeline = filter_pipeline or ActivityFilterPipeline(
            activity_repository=self.activity_repository,
            user_preference_manager=self.user_preference_manager,
            ai_filter=self.ai_filter,
            use_ai_filter=self.use_ai_filter,
            ai_user_info=self.ai_user_info,
            time_filter=self.time_filter,
            use_time_filter=self.use_time_filter,
        )
        self.diff_engine = DiffEngine(self.activity_repository)
        self._last_scan_time: Optional[datetime] = None
        self._is_running = False
        self._scan_lock = asyncio.Lock()  # 防止并发扫描

    async def scan(
            self,
            deep_update: bool,
            notify_diff: bool,
            notify_enrolled_change: bool,
            notify_new_activities: bool,
            no_filter: bool
    ) -> dict[str, Any]:
        if self._scan_lock.locked():
            logger.warning("扫描正在进行中，跳过本次请求")
            return {
                "success": False,
                "error": "扫描正在进行中，请稍后再试",
                "new_db_path": None,
                "old_db_path": None,
                "activity_count": 0,
                "diff": None,
                "enrolled_changes": [],
            }

        async with self._scan_lock:
            return await self._do_scan(
                deep_update=deep_update,
                notify_diff=notify_diff,
                notify_enrolled_change=notify_enrolled_change,
                notify_new_activities=notify_new_activities,
                no_filter=no_filter,
            )

    async def _do_scan(
            self,
            deep_update: bool,
            notify_diff: bool,
            notify_enrolled_change: bool,
            notify_new_activities: bool,
            no_filter: bool
    ) -> dict[str, Any]:
        logger.info("=" * 50)
        logger.info("开始扫描第二课堂活动...")

        result = {
            "success": False,
            "new_db_path": None,
            "old_db_path": None,
            "activity_count": 0,
            "diff": None,
            "enrolled_changes": [],
            "error": None,
        }

        old_db_path = self.db_manager.get_previous_db()
        result["old_db_path"] = old_db_path

        new_db_path = self.db_manager.get_new_db_path()
        result["new_db_path"] = new_db_path
        logger.info(f"新数据库: {new_db_path.name}")

        try:
            async with self.auth_manager.create_session_once() as service:
                logger.debug("会话已创建，开始获取数据...")

                db = SecondClassDB(new_db_path)
                await db.update_all_from_generator(
                    SecondClass.find(apply_ended=False),
                    expand_series=False,
                    deep_update=deep_update
                )

                try:
                    await db.update_enrolled_from_generator(
                        SecondClass.get_participated(),
                        deep_update=deep_update
                    )
                except Exception as e:
                    logger.warning(f"获取已报名活动失败: {e}")

            result["activity_count"] = await self._count_activities(new_db_path)
            logger.info(f"扫描到 {result['activity_count']} 个可报名活动")

            enrolled_count = await self._count_enrolled(new_db_path)
            logger.info(f"已报名 {enrolled_count} 个活动")

            if not no_filter and not notify_new_activities and not notify_enrolled_change and not notify_diff:
                logger.info("仅更新数据库，无需发送详细通知")

            if old_db_path and old_db_path != new_db_path:
                logger.info(f"开始对比{old_db_path.name}和{new_db_path.name}")
                diff = await self.diff_engine.diff(old_db_path, new_db_path)
                result["diff"] = diff
                logger.info(f"差异对比: {diff.get_summary()}")

                enrolled_ids = await self.diff_engine.get_enrolled_ids(new_db_path)
                enrolled_changes = diff.get_enrolled_changes(enrolled_ids)
                result["enrolled_changes"] = enrolled_changes

                if enrolled_changes:
                    logger.info(f"已报名活动有 {len(enrolled_changes)} 处变更")

                    if notify_enrolled_change and self.event_bus:
                        event = EnrolledActivityChangedEvent(
                            changes=enrolled_changes,
                        )
                        await self.event_bus.publish(event)

                if notify_new_activities and diff.added and self.event_bus:
                    self._create_background_task(self._publish_new_activities_event(diff, not no_filter))

                if self.event_bus:
                    completed_event = ScanCompletedEvent(
                        new_db_path=new_db_path,
                        old_db_path=old_db_path,
                        activity_count=result["activity_count"],
                        enrolled_count=enrolled_count,
                        diff=diff,
                    )
                    await self.event_bus.publish(completed_event)

            deleted_count = self.db_manager.cleanup_old_dbs()
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧数据库")

            self._last_scan_time = datetime.now()
            result["success"] = True
            logger.info(f"扫描完成: {new_db_path.name}")

        except Exception as e:
            logger.error(f"扫描失败: {e}")
            traceback.print_exc()
            result["error"] = str(e)
            if new_db_path.exists():
                try:
                    new_db_path.unlink()
                    logger.debug(f"已清理失败的数据库文件: {new_db_path.name}")
                except OSError:
                    pass
            raise

        return result

    async def _count_activities(self, db_path: Path) -> int:
        return await self.activity_repository.count_all(db_path)

    async def _count_enrolled(self, db_path: Path) -> int:
        return await self.activity_repository.count_enrolled(db_path)

    def _create_background_task(self, coro) -> None:
        async def wrapped_coro():
            try:
                await coro
            except Exception as e:
                logger.error(f"后台任务执行失败: {e}")

        task = asyncio.create_task(wrapped_coro())

        def on_task_done(t):
            try:
                t.result()
            except Exception as e:
                logger.error(f"后台任务异常: {e}")

        task.add_done_callback(on_task_done)

    async def _publish_new_activities_event(self, diff, enable_filter: bool = True) -> None:
        if not self.event_bus:
            return

        if not diff or not diff.added:
            return

        try:
            new_activity_ids = [change.activity_id for change in diff.added]
            activities = await self.get_activity_list_by_id(new_activity_ids)

            latest_db = self.db_manager.get_latest_db() or self.db_manager.get_new_db_path()
            filter_result = await self.filter_pipeline.apply(
                activities,
                FilterContext(
                    latest_db=latest_db,
                    enable_filters=enable_filter,
                    include_interested_restore=enable_filter,
                    use_ai_cache=True,
                    force_ai_review=False,
                    ignore_overlap=self.ignore_overlap,
                    source="scanner",
                    allowed_statuses=[Status.APPLYING, Status.PUBLISHED],
                    apply_enrolled_filter=enable_filter,
                ),
            )
            activities = filter_result.kept
            filters_applied = filter_result.non_empty_filtered()

            if not activities and not filters_applied:
                logger.info("筛选后无活动需要通知")
                return

            logger.debug(
                "发布新活动事件: use_ai_filter=%s, ai_keep_reasons_keys=%s, overlap_reasons_keys=%s",
                self.use_ai_filter,
                list(filter_result.ai_keep_reasons.keys()) if self.use_ai_filter else [],
                list(filter_result.overlap_reasons.keys()) if filter_result.overlap_reasons else [],
            )
            event = NewActivitiesFoundEvent(
                activities=activities,
                total_found=len(new_activity_ids),
                filters_applied=filters_applied,
                ai_keep_reasons=filter_result.ai_keep_reasons if self.use_ai_filter else {},
                overlap_reasons=filter_result.overlap_reasons,
            )
            await self.event_bus.publish(event)

            summary_suffix = f"，{'，'.join(filter_result.summaries)}" if filter_result.summaries else ""
            logger.info(f"已发布新活动事件: {len(activities)} 个新活动{summary_suffix}")

        except Exception as e:
            logger.error(f"发布新活动事件失败: {e}")

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

        logger.info(f"检查版本检查器: version_checker={self.version_checker is not None}")
        if self.version_checker:
            logger.info(f"版本检查器 enabled={self.version_checker.enabled}")

        version_check_added = False
        if self.version_checker and self.version_checker.enabled:
            from apscheduler.triggers.cron import CronTrigger

            config = self.version_checker.config
            logger.info(f"正在添加版本检查任务...")
            logger.info(f"配置: day_of_week={config.day_of_week}, "
                        f"hour={config.hour}, minute={config.minute}")

            self.scheduler.add_job(
                self._check_version,
                trigger=CronTrigger(
                    day_of_week=config.day_of_week,
                    hour=config.hour,
                    minute=config.minute,
                ),
                id="version_check",
                replace_existing=True,
                max_instances=1,
            )
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_name = weekday_names[config.day_of_week]
            logger.info(f"版本检查已启动，每周 {weekday_name} "
                        f"{config.hour:02d}:{config.minute:02d}")
            version_check_added = True
        else:
            logger.info("版本检查任务未添加（未启用或未初始化）")

        self.scheduler.start()
        self._is_running = True
        logger.info(f"定时扫描已启动，间隔: {self.interval}分钟")

        if version_check_added:
            job = self.scheduler.get_job("version_check")
            if job and hasattr(job, 'next_run_time') and job.next_run_time:
                logger.info(f"版本检查下次运行时间: {job.next_run_time}")

    async def _check_version(self) -> None:
        logger.info("定时任务触发，开始检查版本更新...")

        if not self.version_checker:
            logger.warning("版本检查器未初始化，跳过检查")
            return

        try:
            logger.info("正在检查更新...")
            result = await self.version_checker.check_for_updates()

            if result is None:
                logger.info("已是最新版本或检查失败（返回 None）")
            elif result.commits_behind > 0:
                logger.info(f"发现新版本！落后 {result.commits_behind} 个 commit")
                logger.info(f"当前版本: {result.current_sha[:7]}, "
                            f"最新版本: {result.latest_sha[:7]}")
                if self.event_bus:
                    event = VersionUpdateEvent(
                        current_sha=result.current_sha,
                        latest_sha=result.latest_sha,
                        commits_behind=result.commits_behind,
                        new_commits=result.new_commits,
                        repo_url=result.repo_url,
                    )
                    await self.event_bus.publish(event)
                    logger.info("已发布 VersionUpdateEvent 事件")
                else:
                    logger.warning("EventBus 未设置，无法发布事件")
            else:
                logger.info("当前已是最新版本，无需通知")

        except Exception as e:
            logger.error(f"版本检查失败: {e}")
            import traceback
            traceback.print_exc()

        logger.info("检查完成")

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
        logger.info(f"开始获取 {len(activity_ids)} 个活动的详情，并发数: {max_concurrent}...")

        sc_instances = [SecondClass(aid, {}) for aid in activity_ids]

        from src.core.services import ActivityUpdateService
        update_service = ActivityUpdateService(self.auth_manager, max_concurrent=max_concurrent)
        update_result = await update_service.update_activities(sc_instances, continue_on_error=True)

        activities = update_result.successful
        if update_result.failed:
            for sc, error in update_result.failed:
                logger.warning(f"获取活动 {sc.id} 失败，可能已删除: {error}")

        logger.info(f"成功获取 {len(activities)}/{len(activity_ids)} 个活动详情")
        return activities
