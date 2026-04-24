"""数据库差异对比引擎"""
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.models import (
    ActivityChange,
    DiffResult,
    FieldChange,
)
from src.core.repositories import ActivityRepository
from src.utils.logger import get_logger

logger = get_logger("diff")

IGNORE_FIELDS = {"scan_timestamp", "deep_scaned", "deep_scaned_time"}

COMPARABLE_FIELDS = (
    "id",
    "name",
    "status",
    "create_time",
    "apply_time",
    "hold_time",
    "tel",
    "valid_hour",
    "apply_num",
    "apply_limit",
    "applied",
    "need_sign_info",
    "module",
    "department",
    "labels",
    "conceive",
    "is_series",
    "place_info",
    "children_id",
    "parent_id",
    "participation_form",
)

JSON_FIELDS = {
    "create_time",
    "apply_time",
    "hold_time",
    "module",
    "department",
    "labels",
    "children_id",
}

BOOLEAN_FIELDS = {"applied", "need_sign_info", "is_series"}


class DiffEngine:
    def __init__(self, activity_repository: ActivityRepository | None = None):
        self.activity_repository = activity_repository or ActivityRepository()

    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        logger.info(f"开始对比数据库: {old_db_path.name} -> {new_db_path.name}")

        old_activities = await self._load_activity_rows(old_db_path)
        new_activities = await self._load_activity_rows(new_db_path)

        old_ids = set(old_activities.keys())
        new_ids = set(new_activities.keys())

        added = []
        removed = []
        modified = []

        for aid in new_ids - old_ids:
            act = new_activities[aid]
            added.append(ActivityChange(
                activity_id=aid,
                activity_name=self._get_activity_name(act),
                change_type="added"
            ))
            logger.debug(f"新增活动: {self._get_activity_name(act)} ({aid})")

        for aid in old_ids - new_ids:
            act = old_activities[aid]
            removed.append(ActivityChange(
                activity_id=aid,
                activity_name=self._get_activity_name(act),
                change_type="removed"
            ))
            logger.debug(f"删除活动: {self._get_activity_name(act)} ({aid})")

        for aid in old_ids & new_ids:
            old_act = old_activities[aid]
            new_act = new_activities[aid]
            field_changes = self._compare_activity(old_act, new_act)
            if field_changes:
                modified.append(ActivityChange(
                    activity_id=aid,
                    activity_name=self._get_activity_name(new_act),
                    change_type="modified",
                    field_changes=field_changes
                ))
                logger.debug(
                    f"修改活动: {self._get_activity_name(new_act)} ({aid}), "
                    f"变化字段: {[fc.field_name for fc in field_changes]}"
                )

        old_scan_time = await self._get_db_scan_time(old_db_path)
        new_scan_time = await self._get_db_scan_time(new_db_path)

        result = DiffResult(
            added=added,
            removed=removed,
            modified=modified,
            old_scan_time=old_scan_time,
            new_scan_time=new_scan_time,
        )
        logger.info(f"对比完成: {result.get_summary()}")
        return result

    def _compare_activity(self, old: dict[str, Any], new: dict[str, Any]) -> list[FieldChange]:
        changes = []

        for field_name in COMPARABLE_FIELDS:
            old_val = self._normalize_field_value(field_name, old.get(field_name))
            new_val = self._normalize_field_value(field_name, new.get(field_name))

            if old_val != new_val:
                changes.append(FieldChange(
                    field_name=field_name,
                    old_value=old_val,
                    new_value=new_val
                ))

        return changes

    async def _load_activity_rows(self, db_path: Path) -> dict[str, dict[str, Any]]:
        activities = await self.activity_repository.list_all_rows(db_path)

        logger.debug(f"从 {db_path.name} 加载了 {len(activities)} 个活动")
        return activities

    @staticmethod
    def _get_activity_name(row: dict[str, Any]) -> str:
        return str(row.get("name") or row.get("id") or "未知活动")

    @staticmethod
    def _normalize_field_value(field_name: str, value: Any) -> Any:
        if value is None:
            return None

        if field_name in JSON_FIELDS:
            if value == "null":
                return None
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        if field_name in BOOLEAN_FIELDS:
            if isinstance(value, str):
                return value not in {"0", "false", "False", ""}
            return bool(value)

        if field_name == "participation_form":
            return str(value)

        return value

    async def get_enrolled_ids(self, db_path: Path) -> set[str]:
        return await self.activity_repository.list_enrolled_ids(db_path)

    async def _get_db_scan_time(self, db_path: Path) -> Optional[datetime]:
        if not db_path or not db_path.exists():
            return None

        try:
            return await self.activity_repository.get_scan_time(db_path)
        except Exception as e:
            logger.warning(f"获取数据库扫描时间失败 {db_path}: {e}")
            traceback.print_exc()

        return None
