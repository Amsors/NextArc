"""活动抓取与快照写入服务。"""

from pathlib import Path
from typing import TYPE_CHECKING

from pyustc.young import SecondClass

from src.core.repositories import ActivityRepository
from src.core.secondclass_db import SecondClassDB
from src.utils.logger import get_logger

from .result import SyncResult

if TYPE_CHECKING:
    from src.core.auth_manager import AuthManager

logger = get_logger("scanning.sync")


class ActivitySyncService:
    """负责从 SecondClass 拉取活动并写入快照数据库。"""

    def __init__(
        self,
        auth_manager: "AuthManager",
        activity_repository: ActivityRepository | None = None,
    ):
        self.auth_manager = auth_manager
        self.activity_repository = activity_repository or ActivityRepository()

    async def sync(self, target_db: Path, deep_update: bool) -> SyncResult:
        db = SecondClassDB(target_db)
        enrolled_error: str | None = None

        async with self.auth_manager.create_session_once():
            logger.debug("会话已创建，开始获取活动数据")
            await db.update_all_from_generator(
                SecondClass.find(apply_ended=False),
                expand_series=False,
                deep_update=deep_update,
            )

            try:
                await db.update_enrolled_from_generator(
                    SecondClass.get_participated(),
                    deep_update=True,
                )
            except Exception as e:
                enrolled_error = str(e)
                logger.warning(f"获取已报名活动失败: {e}")

        activity_count = await self.activity_repository.count_all(target_db)
        enrolled_count = await self.activity_repository.count_enrolled(target_db)
        return SyncResult(
            target_db=target_db,
            activity_count=activity_count,
            enrolled_count=enrolled_count,
            enrolled_error=enrolled_error,
        )
