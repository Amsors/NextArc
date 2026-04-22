"""数据库差异对比引擎"""
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from pyustc.young import SecondClass

from src.models import (
    ActivityChange,
    DiffResult,
    FieldChange,
)
from src.core.repositories import ActivityRepository
from src.utils.logger import get_logger

logger = get_logger("diff")

IGNORE_FIELDS = {"scan_timestamp", "deep_scaned", "deep_scaned_time"}

COMPARABLE_FIELDS = {
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
    "children_id",
    "parent_id",
}


class DiffEngine:
    def __init__(self, activity_repository: ActivityRepository | None = None):
        self.activity_repository = activity_repository or ActivityRepository()

    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        logger.info(f"开始对比数据库: {old_db_path.name} -> {new_db_path.name}")

        old_activities = await self._load_activities(old_db_path)
        new_activities = await self._load_activities(new_db_path)

        old_ids = set(old_activities.keys())
        new_ids = set(new_activities.keys())

        added = []
        removed = []
        modified = []

        for aid in new_ids - old_ids:
            act = new_activities[aid]
            added.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="added"
            ))
            logger.debug(f"新增活动: {act.name} ({aid})")

        for aid in old_ids - new_ids:
            act = old_activities[aid]
            removed.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="removed"
            ))
            logger.debug(f"删除活动: {act.name} ({aid})")

        for aid in old_ids & new_ids:
            old_act = old_activities[aid]
            new_act = new_activities[aid]
            field_changes = self._compare_activity(old_act, new_act)
            if field_changes:
                modified.append(ActivityChange(
                    activity_id=aid,
                    activity_name=new_act.name,
                    change_type="modified",
                    field_changes=field_changes
                ))
                logger.debug(f"修改活动: {new_act.name} ({aid}), 变化字段: {[fc.field_name for fc in field_changes]}")

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

    def _compare_activity(self, old: SecondClass, new: SecondClass) -> list[FieldChange]:
        changes = []

        old_data = old.data
        new_data = new.data

        field_mapping = {
            "name": "itemName",
            "status": "itemStatus",
            "tel": "tel",
            "valid_hour": "validHour",
            "apply_num": "applyNum",
            "apply_limit": "peopleNum",
            "applied": "booleanRegistration",
            "need_sign_info": "needSignInfo",
            "conceive": "conceive",
            "is_series": "itemCategory",
        }

        for display_name, data_key in field_mapping.items():
            old_val = old_data.get(data_key)
            new_val = new_data.get(data_key)

            if old_val != new_val:
                changes.append(FieldChange(
                    field_name=display_name,
                    old_value=old_val,
                    new_value=new_val
                ))

        time_fields = [
            ("apply_time", "applySt", "applyEt"),
            ("hold_time", "st", "et"),
        ]

        for display_name, start_key, end_key in time_fields:
            old_start = old_data.get(start_key)
            old_end = old_data.get(end_key)
            new_start = new_data.get(start_key)
            new_end = new_data.get(end_key)

            if old_start != new_start or old_end != new_end:
                old_val = f"{old_start} ~ {old_end}" if old_start or old_end else None
                new_val = f"{new_start} ~ {new_end}" if new_start or new_end else None
                changes.append(FieldChange(
                    field_name=display_name,
                    old_value=old_val,
                    new_value=new_val
                ))

        old_module = old.module
        new_module = new.module
        if (old_module is None) != (new_module is None) or \
                (old_module and new_module and old_module.text != new_module.text):
            changes.append(FieldChange(
                field_name="module",
                old_value=old_module.text if old_module else None,
                new_value=new_module.text if new_module else None
            ))

        old_dept = old.department
        new_dept = new.department
        if (old_dept is None) != (new_dept is None) or \
                (old_dept and new_dept and old_dept.name != new_dept.name):
            changes.append(FieldChange(
                field_name="department",
                old_value=old_dept.name if old_dept else None,
                new_value=new_dept.name if new_dept else None
            ))

        return changes

    async def _load_activities(self, db_path: Path) -> dict[str, SecondClass]:
        activities = {
            activity.id: activity
            for activity in await self.activity_repository.list_all(db_path)
        }

        logger.debug(f"从 {db_path.name} 加载了 {len(activities)} 个活动")
        return activities

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
