"""活动查询用例服务。"""

from collections.abc import Collection
from pathlib import Path

from pyustc.young import SecondClass, Status

from src.core.repositories import ActivityRepository, SearchMode


class ActivityQueryService:
    """为机器人指令提供活动查询入口。"""

    def __init__(self, activity_repository: ActivityRepository | None = None):
        self.activity_repository = activity_repository or ActivityRepository()

    async def list_valid_activities(self, db_path: Path) -> list[SecondClass]:
        return await self.activity_repository.list_valid(db_path)

    async def search_activities(
        self,
        db_path: Path,
        keyword: str,
        mode: SearchMode | None = None,
    ) -> list[SecondClass]:
        return await self.activity_repository.search(db_path, keyword, mode=mode)

    async def list_enrolled_activities(
        self,
        db_path: Path,
        excluded_statuses: Collection[Status] | None = None,
    ) -> list[SecondClass]:
        activities = await self.activity_repository.list_enrolled(db_path)
        if excluded_statuses:
            excluded = set(excluded_statuses)
            return [activity for activity in activities if activity.status not in excluded]
        return activities

    async def get_activities_by_ids(self, db_path: Path, activity_ids: list[str]) -> list[SecondClass]:
        return await self.activity_repository.get_by_ids(db_path, activity_ids)
