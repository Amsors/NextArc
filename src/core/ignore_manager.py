"""忽略活动数据库管理器

管理用户不感兴趣的活动，持久化存储在 ignore.db 中
"""

import time
from pathlib import Path
from typing import Optional

import aiosqlite

from src.utils.logger import get_logger

logger = get_logger("ignore_manager")


class IgnoreManager:
    """
    忽略活动数据库管理器
    
    功能：
    - 存储用户不感兴趣的活动ID和添加时间
    - 支持批量添加活动到忽略列表
    - 支持检查活动是否被忽略
    - 支持获取所有被忽略的活动ID
    
    数据库结构：
    - activity_id: TEXT PRIMARY KEY - 活动ID
    - added_at: INTEGER - 添加时的Unix时间戳
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化忽略管理器
        
        Args:
            db_path: 数据库文件路径，默认使用项目根目录下的 data/ignore.db
        """
        if db_path is None:
            # 默认路径：项目根目录/data/ignore.db
            project_root = Path(__file__).parent.parent.parent
            db_path = project_root / "data" / "ignore.db"

        self.db_path = Path(db_path)
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库，创建表结构"""
        if self._initialized:
            return

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ignored_activities (
                    activity_id TEXT PRIMARY KEY,
                    added_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_added_at 
                ON ignored_activities(added_at)
            """)
            await db.commit()

        self._initialized = True
        logger.info(f"忽略数据库初始化完成: {self.db_path}")

    async def add_activity(self, activity_id: str) -> bool:
        """
        添加单个活动到忽略列表
        
        Args:
            activity_id: 活动ID
            
        Returns:
            是否添加成功（如果已存在也算成功）
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO ignored_activities (activity_id, added_at)
                    VALUES (?, ?)
                    """,
                    (activity_id, int(time.time()))
                )
                await db.commit()

            logger.debug(f"添加活动到忽略列表: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"添加活动到忽略列表失败: {e}")
            return False

    async def add_activities(self, activity_ids: list[str]) -> tuple[int, int]:
        """
        批量添加活动到忽略列表
        
        Args:
            activity_ids: 活动ID列表
            
        Returns:
            (成功数量, 失败数量)
        """
        await self.initialize()

        if not activity_ids:
            return 0, 0

        success_count = 0
        failed_count = 0
        current_time = int(time.time())

        try:
            async with aiosqlite.connect(self.db_path) as db:
                for activity_id in activity_ids:
                    try:
                        await db.execute(
                            """
                            INSERT OR REPLACE INTO ignored_activities (activity_id, added_at)
                            VALUES (?, ?)
                            """,
                            (activity_id, current_time)
                        )
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"添加活动 {activity_id} 到忽略列表失败: {e}")
                        failed_count += 1

                await db.commit()

            logger.info(f"批量添加忽略活动: 成功 {success_count} 个, 失败 {failed_count} 个")
            return success_count, failed_count

        except Exception as e:
            logger.error(f"批量添加忽略活动失败: {e}")
            return 0, len(activity_ids)

    async def is_ignored(self, activity_id: str) -> bool:
        """
        检查活动是否被忽略
        
        Args:
            activity_id: 活动ID
            
        Returns:
            是否被忽略
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT 1 FROM ignored_activities WHERE activity_id = ?",
                        (activity_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row is not None

        except Exception as e:
            logger.error(f"检查活动忽略状态失败: {e}")
            return False

    async def get_all_ignored_ids(self) -> set[str]:
        """
        获取所有被忽略的活动ID
        
        Returns:
            被忽略的活动ID集合
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT activity_id FROM ignored_activities"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row[0] for row in rows}

        except Exception as e:
            logger.error(f"获取忽略活动列表失败: {e}")
            return set()

    async def remove_activity(self, activity_id: str) -> bool:
        """
        从忽略列表中移除活动
        
        Args:
            activity_id: 活动ID
            
        Returns:
            是否移除成功
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM ignored_activities WHERE activity_id = ?",
                    (activity_id,)
                )
                await db.commit()

            logger.debug(f"从忽略列表移除活动: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"从忽略列表移除活动失败: {e}")
            return False

    async def get_ignored_count(self) -> int:
        """
        获取被忽略的活动数量（异步版本）
        
        Returns:
            被忽略的活动数量
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT COUNT(*) FROM ignored_activities"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

        except Exception as e:
            logger.error(f"获取忽略活动数量失败: {e}")
            return 0

    def get_ignored_count_sync(self) -> int:
        """
        获取被忽略的活动数量（同步版本）
        
        注意：此方法假设数据库已初始化
        
        Returns:
            被忽略的活动数量
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute("SELECT COUNT(*) FROM ignored_activities")
                row = cursor.fetchone()
                return row[0] if row else 0

        except Exception as e:
            logger.error(f"获取忽略活动数量失败: {e}")
            return 0

    async def filter_activities(self, activities: list) -> tuple[list, list]:
        """
        过滤掉被忽略的活动
        
        Args:
            activities: 活动对象列表（需要有 id 属性）
            
        Returns:
            (保留的活动列表, 被过滤掉的活动列表)
        """
        if not activities:
            return [], []

        ignored_ids = await self.get_all_ignored_ids()

        kept = []
        filtered = []

        for activity in activities:
            # 支持 SecondClass 对象或任何有 id 属性的对象
            activity_id = getattr(activity, 'id', None)
            if activity_id is None:
                # 如果是字典类型
                if isinstance(activity, dict):
                    activity_id = activity.get('id')

            if activity_id and activity_id in ignored_ids:
                filtered.append(activity)
            else:
                kept.append(activity)

        if filtered:
            logger.info(f"数据库筛选过滤了 {len(filtered)} 个活动")

        return kept, filtered

    def filter_activities_sync(self, activities: list, ignored_ids: set[str]) -> tuple[list, list]:
        """
        同步方式过滤掉被忽略的活动（用于已知 ignored_ids 的场景）
        
        Args:
            activities: 活动对象列表（需要有 id 属性）
            ignored_ids: 被忽略的活动ID集合
            
        Returns:
            (保留的活动列表, 被过滤掉的活动列表)
        """
        if not activities or not ignored_ids:
            return activities, []

        kept = []
        filtered = []

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None and isinstance(activity, dict):
                activity_id = activity.get('id')

            if activity_id and activity_id in ignored_ids:
                filtered.append(activity)
            else:
                kept.append(activity)

        return kept, filtered
