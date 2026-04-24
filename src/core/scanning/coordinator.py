"""扫描编排服务。"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from pyustc.young import SecondClass, Status

from src.core.events.scan_events import (
    EnrolledActivityChangedEvent,
    NewActivitiesFoundEvent,
    ScanCompletedEvent,
)
from src.core.filtering import ActivityFilterPipeline, FilterContext
from src.core.repositories import ActivityRepository
from src.core.services import ActivityUpdateService
from src.utils.logger import get_logger

from .diff_service import ScanDiffService
from .result import ScanOptions, ScanResult
from .sync_service import ActivitySyncService

if TYPE_CHECKING:
    from src.core.auth_manager import AuthManager
    from src.core.db_manager import DatabaseManager
    from src.core.events import EventBus, EventPublishResult

logger = get_logger("scanning.coordinator")


class ScanCoordinator:
    """编排一次扫描的同步、diff 和事件发布。"""

    def __init__(
        self,
        *,
        db_manager: "DatabaseManager",
        sync_service: ActivitySyncService,
        diff_service: ScanDiffService,
        event_bus: "EventBus | None" = None,
        filter_pipeline: ActivityFilterPipeline | None = None,
        activity_repository: ActivityRepository | None = None,
        activity_update_service: ActivityUpdateService | None = None,
        auth_manager: "AuthManager | None" = None,
        use_ai_filter: bool = False,
        ignore_overlap: bool = False,
    ):
        self.db_manager = db_manager
        self.sync_service = sync_service
        self.diff_service = diff_service
        self.event_bus = event_bus
        self.activity_repository = activity_repository or ActivityRepository()
        self.filter_pipeline = filter_pipeline or ActivityFilterPipeline(
            activity_repository=self.activity_repository,
        )
        self.activity_update_service = activity_update_service
        self.auth_manager = auth_manager
        self.use_ai_filter = use_ai_filter
        self.ignore_overlap = ignore_overlap

    async def scan(self, options: ScanOptions) -> ScanResult:
        logger.info("=" * 50)
        logger.info("开始扫描第二课堂活动...")

        old_db_path = self.db_manager.get_previous_db()
        new_db_path = self.db_manager.get_new_db_path()
        result = ScanResult(new_db_path=new_db_path, old_db_path=old_db_path)
        logger.info(f"新数据库: {new_db_path.name}")

        try:
            sync_result = await self.sync_service.sync(new_db_path, options.deep_update)
            result.activity_count = sync_result.activity_count
            result.enrolled_count = sync_result.enrolled_count
            logger.info(f"扫描到 {result.activity_count} 个可报名活动")
            logger.info(f"已报名 {result.enrolled_count} 个活动")

            if (
                not options.no_filter
                and not options.notify_new_activities
                and not options.notify_enrolled_change
                and not options.notify_diff
            ):
                logger.info("仅更新数据库，无需发送详细通知")

            if old_db_path and old_db_path != new_db_path:
                await self._handle_diff(old_db_path, new_db_path, options, result)

            deleted_count = self.db_manager.cleanup_old_dbs()
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧数据库")

            result.success = True
            logger.info(f"扫描完成: {new_db_path.name}")
            return result

        except Exception as e:
            logger.error(f"扫描失败: {e}", exc_info=True)
            result.error = str(e)
            if new_db_path.exists():
                try:
                    new_db_path.unlink()
                    logger.debug(f"已清理失败的数据库文件: {new_db_path.name}")
                except OSError:
                    pass
            raise

    async def _handle_diff(
        self,
        old_db_path: Path,
        new_db_path: Path,
        options: ScanOptions,
        result: ScanResult,
    ) -> None:
        logger.info(f"开始对比{old_db_path.name}和{new_db_path.name}")
        diff = await self.diff_service.diff(old_db_path, new_db_path)
        result.diff = diff
        logger.info(f"差异对比: {diff.get_summary()}")

        enrolled_changes = await self.diff_service.get_enrolled_changes(diff, new_db_path)
        result.enrolled_changes = enrolled_changes

        if enrolled_changes:
            logger.info(f"已报名活动有 {len(enrolled_changes)} 处变更")
            if options.notify_enrolled_change and self.event_bus:
                publish_result = await self.event_bus.publish(
                    EnrolledActivityChangedEvent(changes=enrolled_changes)
                )
                if options.wait_for_notifications:
                    result.notification_errors.extend(publish_result.error_messages)

        if options.notify_new_activities and diff.added and self.event_bus:
            if options.wait_for_notifications:
                try:
                    publish_result = await self._publish_new_activities_event(
                        diff,
                        enable_filter=not options.no_filter,
                    )
                    if publish_result:
                        result.notification_errors.extend(publish_result.error_messages)
                except Exception as e:
                    logger.error(f"发布新活动事件失败: {e}", exc_info=True)
                    result.notification_errors.append(f"NewActivitiesFoundEvent: {e}")
            else:
                self._create_background_task(
                    self._publish_new_activities_event(diff, enable_filter=not options.no_filter)
                )

        if self.event_bus:
            completed_event = ScanCompletedEvent(
                new_db_path=new_db_path,
                old_db_path=old_db_path,
                activity_count=result.activity_count,
                enrolled_count=result.enrolled_count,
                diff=diff,
            )
            publish_result = await self.event_bus.publish(completed_event)
            if options.wait_for_notifications:
                result.notification_errors.extend(publish_result.error_messages)

    def _create_background_task(self, coro) -> None:
        async def wrapped_coro():
            publish_result = await coro
            if publish_result and not publish_result.success:
                logger.error(
                    "后台事件发布存在失败: %s",
                    "; ".join(publish_result.error_messages),
                )
            return publish_result

        task = asyncio.create_task(wrapped_coro())

        def on_task_done(t):
            try:
                t.result()
            except Exception as e:
                logger.error(f"后台任务异常: {e}", exc_info=True)

        task.add_done_callback(on_task_done)

    async def _publish_new_activities_event(
        self,
        diff,
        enable_filter: bool = True,
    ) -> "EventPublishResult | None":
        if not self.event_bus:
            return None

        if not diff or not diff.added:
            return None

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
            return None

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
        publish_result = await self.event_bus.publish(event)

        summary_suffix = f"，{'，'.join(filter_result.summaries)}" if filter_result.summaries else ""
        logger.info(f"已发布新活动事件: {len(activities)} 个新活动{summary_suffix}")
        return publish_result

    async def get_activity_list_by_id(
        self,
        activity_ids: list[str],
        max_concurrent: int = 5,
    ) -> list[SecondClass]:
        logger.info(f"开始获取 {len(activity_ids)} 个活动的详情，并发数: {max_concurrent}...")

        sc_instances = [SecondClass(aid, {}) for aid in activity_ids]
        update_service = self.activity_update_service
        if update_service is None:
            if self.auth_manager is None:
                raise RuntimeError("ActivityUpdateService 或 AuthManager 未初始化")
            update_service = ActivityUpdateService(self.auth_manager, max_concurrent=max_concurrent)

        update_result = await update_service.update_activities(
            sc_instances,
            max_concurrent=max_concurrent,
            continue_on_error=True,
        )

        if update_result.failed:
            for sc, error in update_result.failed:
                logger.warning(f"获取活动 {sc.id} 失败，可能已删除: {error}")

        logger.info(f"成功获取 {len(update_result.successful)}/{len(activity_ids)} 个活动详情")
        return update_result.successful
