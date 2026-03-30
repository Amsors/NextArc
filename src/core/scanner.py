"""定时扫描器"""
import asyncio
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pyustc.young import SecondClass

from src.core.secondclass_db import SecondClassDB
from src.utils.logger import get_logger
from .ai_filter import AIFilter
from .auth_manager import AuthManager
from .db_manager import DatabaseManager
from .diff_engine import DiffEngine
from .enrolled_filter import EnrolledFilter
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
    """
    定时扫描第二课堂活动
    - 使用 apscheduler 调度定时任务
    - 创建新的时间戳数据库
    - 对比差异并推送通知
    """

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
        self.scheduler = AsyncIOScheduler()
        self.diff_engine = DiffEngine()
        self._last_scan_time: Optional[datetime] = None
        self._is_running = False

    async def scan(
            self,
            deep_update: bool,
            notify_diff: bool,
            notify_enrolled_change: bool,
            notify_new_activities: bool,
            no_filter: bool
    ) -> dict[str, Any]:
        """
        执行一次扫描
        
        Args:
            notify_new_activities: 是否通知新活动
            no_filter: 是否对新活动进行筛选
            notify_enrolled_change: 是否通知已报名活动的更新
            notify_diff: 是否显示数据库差异
            deep_update: 是否深度更新数据库（包含已报名活动）

        Returns:
            扫描结果统计
        """
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
            # YouthService 使用 ContextVar，必须保持同一个上下文
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
                    enrolled_ids = await EnrolledFilter.get_enrolled_ids_from_db(new_db_path)
                    # 后台执行，避免阻塞定时扫描和 WebSocket 心跳
                    self._create_background_task(self._publish_new_activities_event(diff, not no_filter, enrolled_ids))

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
        """统计数据库中的活动数量"""
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM all_secondclass") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def _count_enrolled(self, db_path: Path) -> int:
        """统计已报名活动数量"""
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM enrolled_secondclass") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    def _create_background_task(self, coro) -> None:
        """创建后台任务（带异常处理）"""

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

    async def _publish_new_activities_event(self, diff, enable_filter: bool = True,
                                            enrolled_ids: set[str] = None) -> None:
        """发布新活动发现事件"""
        if not self.event_bus:
            return

        if not diff or not diff.added:
            return

        try:
            new_activity_ids = [change.activity_id for change in diff.added]
            activities = await self.get_activity_list_by_id(new_activity_ids)
            ai_filtered = []
            time_filtered = []
            db_filtered = []
            enrolled_filtered = []

            enrolled_ids = enrolled_ids or set()
            enrolled_filter = EnrolledFilter(enrolled_ids)

            if enable_filter:
                restored_activities = []
                if self.user_preference_manager:
                    activities, restored_activities = \
                        await self.user_preference_manager.restore_interested_activities(activities)
                    if restored_activities:
                        logger.info(f"从感兴趣白名单恢复了 {len(restored_activities)} 个活动")

                # 筛选掉已报名的活动
                if enrolled_ids:
                    logger.info(f"使用已报名筛选检查 {len(activities)} 个新活动...")
                    activities, enrolled_filtered = enrolled_filter.filter_activities(activities)

                    if enrolled_filtered:
                        logger.info(f"已报名筛选过滤了 {len(enrolled_filtered)} 个活动")

                    if not activities and not restored_activities:
                        logger.info("已报名筛选后无活动需要通知（全部已报名）")
                        return

                # 应用数据库筛选（标记为不感兴趣的活动）
                db_filtered = []
                if self.user_preference_manager:
                    logger.info(f"使用数据库筛选检查 {len(activities)} 个新活动...")
                    activities, db_filtered = await self.user_preference_manager.filter_activities(activities)

                    if not activities and not restored_activities:
                        logger.info("数据库筛选后无活动需要通知（全部被用户标记为不感兴趣）")
                        return

                # 如果启用时间筛选，则进行筛选
                if self.use_time_filter and self.time_filter:
                    logger.info(f"使用时间筛选检查 {len(activities)} 个新活动...")
                    activities, time_filtered = self.time_filter.filter_activities(activities)

                    if not activities:
                        logger.info("时间筛选后无活动需要通知")
                        return

                # 如果启用 AI 筛选，则进行筛选
                if self.use_ai_filter and self.ai_filter and self.ai_user_info:
                    logger.info(f"使用 AI 筛选 {len(activities)} 个新活动...")
                    activities, ai_filtered_result = await self.ai_filter.filter_activities(
                        activities,
                        self.ai_user_info,
                        write_to_db=True,
                        prefer_cached=True,
                        preference_manager=self.user_preference_manager,
                    )
                    ai_filtered = ai_filtered_result

                    if not activities and not restored_activities:
                        logger.info("AI 筛选后无活动需要通知")

            # 将恢复的活动加回到最终列表
            if restored_activities:
                activities = restored_activities + activities
                logger.info(
                    f"最终活动列表包含 {len(restored_activities)} 个白名单活动"
                    f"和 {len(activities) - len(restored_activities)} 个通过筛选的活动")

            event = NewActivitiesFoundEvent(
                activities=activities,
                total_found=len(new_activity_ids),
                filters_applied={
                    "db": db_filtered,
                    "time": time_filtered,
                    "ai": ai_filtered,
                    "enrolled": enrolled_filtered,
                },
            )
            await self.event_bus.publish(event)

            logger.info(f"已发布新活动事件: {len(activities)} 个新活动"
                        f"{'，' + str(len(enrolled_filtered)) + ' 个已报名被过滤' if enrolled_filtered else ''}"
                        f"{'，' + str(len(db_filtered)) + ' 个被数据库过滤' if db_filtered else ''}"
                        f"{'，' + str(len(ai_filtered)) + ' 个被 AI 过滤' if ai_filtered else ''}"
                        f"{'，' + str(len(time_filtered)) + ' 个被时间过滤' if time_filtered else ''}")

        except Exception as e:
            logger.error(f"发布新活动事件失败: {e}")

    def start(self) -> None:
        """启动定时任务"""
        if self._is_running:
            logger.warning("定时扫描已在运行")
            return

        self.scheduler.add_job(
            self.scan,
            trigger=IntervalTrigger(minutes=self.interval),
            id="activity_scan",
            replace_existing=True,
            max_instances=1,  # 防止任务重叠
            kwargs={
                "deep_update": True,
                "notify_diff": False,
                "notify_new_activities": True,
                "no_filter": False,
                "notify_enrolled_change": True,
            }
        )

        # 添加版本检查任务（如果启用）
        if self.version_checker and self.version_checker.enabled:
            from apscheduler.triggers.cron import CronTrigger

            config = self.version_checker.config
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
        
        self.scheduler.start()
        self._is_running = True
        logger.info(f"定时扫描已启动，间隔: {self.interval}分钟")

    async def _check_version(self) -> None:
        """执行版本检查"""
        if not self.version_checker:
            return

        try:
            result = await self.version_checker.check_for_updates()
            if result and result.commits_behind > 0:
                logger.info(f"发现新版本，落后 {result.commits_behind} 个 commit")
                if self.event_bus:
                    event = VersionUpdateEvent(
                        current_sha=result.current_sha,
                        latest_sha=result.latest_sha,
                        commits_behind=result.commits_behind,
                        new_commits=result.new_commits,
                        repo_url=result.repo_url,
                    )
                    await self.event_bus.publish(event)
            else:
                logger.debug("当前已是最新版本，无需通知")
        except Exception as e:
            logger.error(f"版本检查失败: {e}")

    def stop(self) -> None:
        """停止定时任务"""
        if not self._is_running:
            return

        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("定时扫描已停止")

    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._is_running

    def get_last_scan_time(self) -> Optional[datetime]:
        """获取上次扫描时间"""
        return self._last_scan_time

    def get_next_scan_time(self) -> Optional[datetime]:
        """获取下次扫描时间"""
        if not self._is_running:
            return None

        job = self.scheduler.get_job("activity_scan")
        if job and job.next_run_time:
            return job.next_run_time
        return None

    async def get_activity_list_by_id(
            self,
            activity_ids: list[str],
            max_concurrent: int = 5
    ) -> list[SecondClass]:
        """
        根据活动ID列表获取活动详情（支持并发）

        Args:
            activity_ids: 活动ID列表
            max_concurrent: 最大并发数

        Returns:
            SecondClass 对象列表（仅包含成功获取的活动）
        """
        logger.info(f"开始获取 {len(activity_ids)} 个活动的详情，并发数: {max_concurrent}...")

        activities: list[SecondClass] = []

        async with self.auth_manager.create_session_once() as service:
            sc_instances = [SecondClass(aid, None) for aid in activity_ids]

            from .batch_updater import SecondClassBatchUpdater
            updater = SecondClassBatchUpdater(max_concurrent)

            successful, failed = await updater.update_batch(sc_instances, continue_on_error=True)
            activities.extend(successful)

            if failed:
                for sc, error in failed:
                    logger.warning(f"获取活动 {sc.id} 失败，可能已删除: {error}")

        logger.info(f"成功获取 {len(activities)}/{len(activity_ids)} 个活动详情")
        return activities
