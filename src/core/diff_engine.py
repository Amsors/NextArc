"""数据库差异对比引擎"""
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from pyustc.young import SecondClass

from src.models import (
    ActivityChange,
    DiffResult,
    FieldChange,
    secondclass_from_db_row,
)
from src.utils.logger import get_logger

logger = get_logger("diff")

# 忽略字段（不参与差异比较）
IGNORE_FIELDS = {"scan_timestamp", "deep_scaned", "deep_scaned_time"}

# 比较的字段列表
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
    """对比两个数据库状态的差异"""

    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        """对比两个数据库，返回差异结果"""
        logger.info(f"开始对比数据库: {old_db_path.name} -> {new_db_path.name}")

        old_activities = await self._load_activities(old_db_path)
        new_activities = await self._load_activities(new_db_path)

        old_ids = set(old_activities.keys())
        new_ids = set(new_activities.keys())

        added = []
        removed = []
        modified = []

        # 新增
        for aid in new_ids - old_ids:
            act = new_activities[aid]
            added.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="added"
            ))
            logger.debug(f"新增活动: {act.name} ({aid})")

        # 删除
        for aid in old_ids - new_ids:
            act = old_activities[aid]
            removed.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="removed"
            ))
            logger.debug(f"删除活动: {act.name} ({aid})")

        # 修改
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
        """对比单个活动的字段变化"""
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

        # 比较时间字段
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

        # 比较 module
        old_module = old.module
        new_module = new.module
        if (old_module is None) != (new_module is None) or \
                (old_module and new_module and old_module.text != new_module.text):
            changes.append(FieldChange(
                field_name="module",
                old_value=old_module.text if old_module else None,
                new_value=new_module.text if new_module else None
            ))

        # 比较 department
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
        """从数据库加载所有活动"""
        activities = {}

        if not db_path.exists():
            logger.warning(f"数据库不存在: {db_path}")
            return activities

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute("SELECT * FROM all_secondclass") as cursor:
                    async for row in cursor:
                        row_dict = dict(row)
                        activity = secondclass_from_db_row(row_dict)
                        activities[activity.id] = activity
            except Exception as e:
                logger.error(f"加载数据库失败 {db_path}: {e}")
                raise

        logger.debug(f"从 {db_path.name} 加载了 {len(activities)} 个活动")
        return activities

    async def get_enrolled_ids(self, db_path: Path) -> set[str]:
        """获取已报名活动 ID 集合"""
        enrolled_ids = set()

        if not db_path.exists():
            return enrolled_ids

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute("SELECT id FROM enrolled_secondclass") as cursor:
                    async for row in cursor:
                        enrolled_ids.add(row["id"])
            except Exception as e:
                logger.error(f"加载已报名活动失败 {db_path}: {e}")

        logger.debug(f"已报名活动数量: {len(enrolled_ids)}")
        return enrolled_ids

    async def _get_db_scan_time(self, db_path: Path) -> Optional[datetime]:
        """获取数据库的扫描时间"""
        if not db_path or not db_path.exists():
            return None

        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                        "SELECT MIN(scan_timestamp) as min_ts FROM all_secondclass"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return datetime.fromtimestamp(row[0])
        except Exception as e:
            logger.warning(f"获取数据库扫描时间失败 {db_path}: {e}")
            traceback.print_exc()

        return None
