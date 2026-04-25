"""SecondClass 深度更新服务。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyustc.young import SecondClass

from src.core.batch_updater import SecondClassBatchUpdater
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core.auth_manager import AuthManager

logger = get_logger("service.activity_update")


@dataclass
class ActivityUpdateResult:
    """活动深度更新结果。"""

    successful: list[SecondClass]
    failed: list[tuple[SecondClass, Exception]]

    @property
    def success_count(self) -> int:
        return len(self.successful)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


@dataclass
class ChildrenFetchResult:
    """系列活动子活动获取和深度更新结果。"""

    parent: SecondClass
    children: list[SecondClass]
    update_result: ActivityUpdateResult


class ActivityUpdateService:
    """统一处理 SecondClass.update() 的认证上下文、并发和失败策略。"""

    def __init__(self, auth_manager: "AuthManager", max_concurrent: int = 5):
        self.auth_manager = auth_manager
        self.max_concurrent = max_concurrent

    async def update_activities(
        self,
        activities: list[SecondClass],
        max_concurrent: int | None = None,
        continue_on_error: bool = True,
    ) -> ActivityUpdateResult:
        if not activities:
            return ActivityUpdateResult(successful=[], failed=[])

        async with self.auth_manager.create_session_once():
            return await self._update_activities_in_current_session(
                activities,
                max_concurrent=max_concurrent,
                continue_on_error=continue_on_error,
            )

    async def _update_activities_in_current_session(
        self,
        activities: list[SecondClass],
        max_concurrent: int | None = None,
        continue_on_error: bool = True,
    ) -> ActivityUpdateResult:
        """在调用方已建立的 YouthService 上下文中批量更新活动。"""
        if not activities:
            return ActivityUpdateResult(successful=[], failed=[])

        concurrency = max_concurrent or self.max_concurrent
        updater = SecondClassBatchUpdater(concurrency)

        successful, failed = await updater.update_batch(
            activities,
            continue_on_error=continue_on_error,
        )

        if failed:
            for activity, error in failed:
                logger.warning(f"深度更新活动 {activity.id} 失败: {error}")

        return ActivityUpdateResult(successful=successful, failed=failed)

    async def update_activity(self, activity: SecondClass) -> tuple[bool, Exception | None]:
        result = await self.update_activities([activity], continue_on_error=False)
        if result.failed:
            return False, result.failed[0][1]
        return True, None

    async def fetch_activity(self, activity_id: str) -> SecondClass:
        activity = SecondClass(activity_id, {})
        success, error = await self.update_activity(activity)
        if not success:
            raise RuntimeError(f"更新活动 {activity_id} 失败: {error}") from error
        return activity

    async def fetch_children(self, activity_id: str) -> tuple[SecondClass, list[SecondClass]]:
        parent = SecondClass(activity_id, {})
        async with self.auth_manager.create_session_once():
            await parent.update()
            if not parent.is_series:
                return parent, []
            children = await parent.get_children()
        return parent, children

    async def fetch_children_with_updates(
        self,
        activity_id: str,
        child_filter: Callable[[SecondClass], bool] | None = None,
        max_concurrent: int | None = None,
        continue_on_error: bool = True,
    ) -> ChildrenFetchResult:
        """用同一个认证会话获取系列活动子活动，并深度更新需要展示的子活动。"""
        parent = SecondClass(activity_id, {})

        async with self.auth_manager.create_session_once():
            await parent.update()
            if not parent.is_series:
                return ChildrenFetchResult(
                    parent=parent,
                    children=[],
                    update_result=ActivityUpdateResult(successful=[], failed=[]),
                )

            children = await parent.get_children()
            children_to_update = (
                [child for child in children if child_filter(child)]
                if child_filter
                else children
            )
            update_result = await self._update_activities_in_current_session(
                children_to_update,
                max_concurrent=max_concurrent,
                continue_on_error=continue_on_error,
            )

        return ChildrenFetchResult(
            parent=parent,
            children=children_to_update,
            update_result=update_result,
        )
