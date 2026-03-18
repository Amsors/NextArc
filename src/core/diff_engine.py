"""数据库差异对比引擎"""

from pathlib import Path
from typing import Any

import aiosqlite

from src.models import Activity, ActivityChange, DiffResult, FieldChange
from src.utils.logger import get_logger

logger = get_logger("diff")


class DiffEngine:
    """
    对比两个数据库状态的差异
    - 比较 all_secondclass 表
    - 生成新增/删除/修改列表
    """
    
    # 需要忽略的字段（不参与差异比较）
    IGNORE_FIELDS = {"scan_timestamp"}
    
    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        """
        对比两个数据库，返回差异结果
        
        Args:
            old_db_path: 旧数据库路径
            new_db_path: 新数据库路径
            
        Returns:
            DiffResult 差异结果
        """
        logger.info(f"开始对比数据库: {old_db_path.name} -> {new_db_path.name}")
        
        # 加载两个数据库的活动数据
        old_activities = await self._load_activities(old_db_path)
        new_activities = await self._load_activities(new_db_path)
        
        old_ids = set(old_activities.keys())
        new_ids = set(new_activities.keys())
        
        added = []
        removed = []
        modified = []
        
        # 新增：在新数据库中但不在旧数据库中
        for aid in new_ids - old_ids:
            act = new_activities[aid]
            added.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="added"
            ))
            logger.debug(f"新增活动: {act.name} ({aid})")
        
        # 删除：在旧数据库中但不在新数据库中
        for aid in old_ids - new_ids:
            act = old_activities[aid]
            removed.append(ActivityChange(
                activity_id=aid,
                activity_name=act.name,
                change_type="removed"
            ))
            logger.debug(f"删除活动: {act.name} ({aid})")
        
        # 修改：在两个数据库中都存在，但字段有变化
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
        
        result = DiffResult(added=added, removed=removed, modified=modified)
        logger.info(f"对比完成: {result.get_summary()}")
        return result
    
    def _compare_activity(self, old: Activity, new: Activity) -> list[FieldChange]:
        """
        对比单个活动的字段变化，忽略 scan_timestamp
        
        Args:
            old: 旧活动数据
            new: 新活动数据
            
        Returns:
            字段变化列表
        """
        changes = []
        
        # 获取所有字段（使用 model_fields 从 Pydantic 模型获取）
        all_fields = set(Activity.model_fields.keys())
        
        for field in all_fields:
            if field in self.IGNORE_FIELDS:
                continue
            
            old_val = getattr(old, field)
            new_val = getattr(new, field)
            
            if old_val != new_val:
                changes.append(FieldChange(
                    field_name=field,
                    old_value=old_val,
                    new_value=new_val
                ))
        
        return changes
    
    async def _load_activities(self, db_path: Path) -> dict[str, Activity]:
        """
        从数据库加载所有活动
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            以 activity_id 为键的 Activity 字典
        """
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
                        activity = Activity.from_db_row(row_dict)
                        activities[activity.id] = activity
            except Exception as e:
                logger.error(f"加载数据库失败 {db_path}: {e}")
                raise
        
        logger.debug(f"从 {db_path.name} 加载了 {len(activities)} 个活动")
        return activities
    
    async def get_enrolled_ids(self, db_path: Path) -> set[str]:
        """
        获取用户已报名的活动 ID 集合
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            已报名活动 ID 集合
        """
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
