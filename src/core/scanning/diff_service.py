"""扫描差异计算服务。"""

from pathlib import Path

from src.core.diff_engine import DiffEngine
from src.core.repositories import ActivityRepository
from src.models.diff_result import ActivityChange, DiffResult


class ScanDiffService:
    """封装扫描阶段需要的 diff 与已报名变更判断。"""

    def __init__(
        self,
        diff_engine: DiffEngine | None = None,
        activity_repository: ActivityRepository | None = None,
    ):
        self.activity_repository = activity_repository or ActivityRepository()
        self.diff_engine = diff_engine or DiffEngine(self.activity_repository)

    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        return await self.diff_engine.diff(old_db_path, new_db_path)

    async def get_enrolled_changes(
        self,
        diff: DiffResult,
        new_db_path: Path,
    ) -> list[ActivityChange]:
        enrolled_ids = await self.diff_engine.get_enrolled_ids(new_db_path)
        return diff.get_enrolled_changes(enrolled_ids)
