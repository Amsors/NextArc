"""用户偏好数据库管理器

管理用户的活动偏好设置，包括：
- 不感兴趣的活动（ignored_activities 表）
- 感兴趣的活动（interested_activities 表）

支持从旧的 ignore.db 自动迁移数据。
"""

import time
from pathlib import Path
from typing import Optional

import aiosqlite

from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("user_preference_manager")


class UserPreferenceManager:
    """
    用户偏好数据库管理器

    功能：
    - 存储用户不感兴趣的活动ID和添加时间
    - 存储用户感兴趣的活动ID和添加时间
    - 支持从旧的 ignore.db 自动迁移数据
    - 支持白名单恢复：感兴趣的活动会绕过所有筛选

    数据库结构：
    - ignored_activities: activity_id TEXT PRIMARY KEY, added_at INTEGER
    - interested_activities: activity_id TEXT PRIMARY KEY, added_at INTEGER
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化用户偏好管理器

        Args:
            db_path: 数据库文件路径，默认使用项目根目录下的 data/user_preference.db
                      支持绝对路径或相对于项目根目录的路径
        """
        if db_path is None:
            # 默认路径：项目根目录/data/user_preference.db
            project_root = Path(__file__).parent.parent.parent
            db_path = project_root / "data" / "user_preference.db"
        else:
            # 处理相对路径（相对于项目根目录）
            db_path = Path(db_path)
            if not db_path.is_absolute():
                project_root = Path(__file__).parent.parent.parent
                db_path = project_root / db_path

        self.db_path = db_path.resolve()  # 转换为绝对路径
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库，创建表结构，执行数据迁移"""
        if self._initialized:
            return

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查是否需要从旧数据库迁移
        await self._migrate_from_old_db()

        async with aiosqlite.connect(self.db_path) as db:
            # 创建不感兴趣活动表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ignored_activities (
                    activity_id TEXT PRIMARY KEY,
                    added_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ignored_added_at 
                ON ignored_activities(added_at)
            """)

            # 创建感兴趣活动表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS interested_activities (
                    activity_id TEXT PRIMARY KEY,
                    added_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_interested_added_at 
                ON interested_activities(added_at)
            """)

            await db.commit()

        self._initialized = True
        logger.info(f"用户偏好数据库初始化完成: {self.db_path}")

    async def _migrate_from_old_db(self) -> None:
        """
        从旧的 ignore.db 迁移数据

        如果存在旧的 ignore.db，将其数据迁移到新的数据库结构，
        迁移完成后删除旧数据库。
        """
        old_db_path = self.db_path.parent / "ignore.db"

        if not old_db_path.exists():
            return

        if self.db_path.exists():
            # 新数据库已存在，不需要迁移
            logger.info("新数据库已存在，跳过数据迁移")
            try:
                old_db_path.unlink()
                logger.info(f"已删除旧数据库: {old_db_path}")
            except OSError as e:
                logger.warning(f"删除旧数据库失败: {e}")
            return

        logger.info(f"检测到旧数据库，开始迁移: {old_db_path}")

        try:
            # 创建新数据库
            async with aiosqlite.connect(self.db_path) as new_db:
                # 创建表
                await new_db.execute("""
                    CREATE TABLE IF NOT EXISTS ignored_activities (
                        activity_id TEXT PRIMARY KEY,
                        added_at INTEGER NOT NULL
                    )
                """)

                # 从旧数据库读取数据
                async with aiosqlite.connect(old_db_path) as old_db:
                    async with old_db.execute(
                            "SELECT activity_id, added_at FROM ignored_activities"
                    ) as cursor:
                        rows = await cursor.fetchall()

                # 迁移数据
                migrated_count = 0
                for row in rows:
                    try:
                        await new_db.execute(
                            """
                            INSERT INTO ignored_activities (activity_id, added_at)
                            VALUES (?, ?)
                            """,
                            (row[0], row[1])
                        )
                        migrated_count += 1
                    except Exception as e:
                        logger.warning(f"迁移活动 {row[0]} 失败: {e}")

                await new_db.commit()

            logger.info(f"数据迁移完成: {migrated_count} 个活动已迁移")

            # 删除旧数据库
            try:
                old_db_path.unlink()
                logger.info(f"已删除旧数据库: {old_db_path}")
            except OSError as e:
                logger.warning(f"删除旧数据库失败: {e}")

        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            # 如果迁移失败，尝试清理可能部分创建的新数据库
            if self.db_path.exists():
                try:
                    self.db_path.unlink()
                except OSError:
                    pass
            raise

    # ==================== ignored_activities 表操作 ====================

    async def add_ignored_activity(self, activity_id: str) -> bool:
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

    async def add_ignored_activities(self, activity_ids: list[str]) -> tuple[int, int]:
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

    async def remove_ignored_activity(self, activity_id: str) -> bool:
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

    # ==================== interested_activities 表操作 ====================

    async def add_interested_activity(self, activity_id: str) -> bool:
        """
        添加单个活动到感兴趣列表

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
                    INSERT OR REPLACE INTO interested_activities (activity_id, added_at)
                    VALUES (?, ?)
                    """,
                    (activity_id, int(time.time()))
                )
                await db.commit()

            logger.debug(f"添加活动到感兴趣列表: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"添加活动到感兴趣列表失败: {e}")
            return False

    async def add_interested_activities(self, activity_ids: list[str]) -> tuple[int, int]:
        """
        批量添加活动到感兴趣列表

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
                            INSERT OR REPLACE INTO interested_activities (activity_id, added_at)
                            VALUES (?, ?)
                            """,
                            (activity_id, current_time)
                        )
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"添加活动 {activity_id} 到感兴趣列表失败: {e}")
                        failed_count += 1

                await db.commit()

            logger.info(f"批量添加感兴趣活动: 成功 {success_count} 个, 失败 {failed_count} 个")
            return success_count, failed_count

        except Exception as e:
            logger.error(f"批量添加感兴趣活动失败: {e}")
            return 0, len(activity_ids)

    async def is_interested(self, activity_id: str) -> bool:
        """
        检查活动是否被标记为感兴趣

        Args:
            activity_id: 活动ID

        Returns:
            是否已标记为感兴趣
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT 1 FROM interested_activities WHERE activity_id = ?",
                        (activity_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row is not None

        except Exception as e:
            logger.error(f"检查活动感兴趣状态失败: {e}")
            return False

    async def get_all_interested_ids(self) -> set[str]:
        """
        获取所有被标记为感兴趣的活动ID

        Returns:
            感兴趣的活动ID集合
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT activity_id FROM interested_activities"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row[0] for row in rows}

        except Exception as e:
            logger.error(f"获取感兴趣活动列表失败: {e}")
            return set()

    async def remove_interested_activity(self, activity_id: str) -> bool:
        """
        从感兴趣列表中移除活动

        Args:
            activity_id: 活动ID

        Returns:
            是否移除成功
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM interested_activities WHERE activity_id = ?",
                    (activity_id,)
                )
                await db.commit()

            logger.debug(f"从感兴趣列表移除活动: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"从感兴趣列表移除活动失败: {e}")
            return False

    async def get_interested_count(self) -> int:
        """
        获取感兴趣的活动数量（异步版本）

        Returns:
            感兴趣的活动数量
        """
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT COUNT(*) FROM interested_activities"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

        except Exception as e:
            logger.error(f"获取感兴趣活动数量失败: {e}")
            return 0

    def get_interested_count_sync(self) -> int:
        """
        获取感兴趣的活动数量（同步版本）

        注意：此方法假设数据库已初始化

        Returns:
            感兴趣的活动数量
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute("SELECT COUNT(*) FROM interested_activities")
                row = cursor.fetchone()
                return row[0] if row else 0

        except Exception as e:
            logger.error(f"获取感兴趣活动数量失败: {e}")
            return 0

    # ==================== 筛选相关操作 ====================

    async def filter_activities(self, activities: list) -> tuple[list, list[FilteredActivity]]:
        """
        过滤掉被忽略的活动（同时考虑感兴趣白名单）

        逻辑：
        1. 如果活动在 interested 列表中，保留（绕过忽略）
        2. 如果活动在 ignored 列表中，过滤
        3. 其他活动保留

        Args:
            activities: 活动对象列表（需要有 id 属性）

        Returns:
            (保留的活动列表, 被过滤掉的 FilteredActivity 列表)
        """
        if not activities:
            return [], []

        interested_ids = await self.get_all_interested_ids()
        ignored_ids = await self.get_all_ignored_ids()

        kept = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            # 支持 SecondClass 对象或任何有 id 属性的对象
            activity_id = getattr(activity, 'id', None)
            if activity_id is None:
                # 如果是字典类型
                if isinstance(activity, dict):
                    activity_id = activity.get('id')

            # 感兴趣白名单优先
            if activity_id and activity_id in interested_ids:
                kept.append(activity)
                continue

            if activity_id and activity_id in ignored_ids:
                filtered.append(FilteredActivity(
                    activity=activity,
                    reason="用户已标记为不感兴趣",
                    filter_type="ignore"
                ))
            else:
                kept.append(activity)

        if filtered:
            logger.info(f"数据库筛选过滤了 {len(filtered)} 个活动")

        return kept, filtered

    def filter_activities_sync(self, activities: list, ignored_ids: set[str], interested_ids: set[str] = None) -> tuple[
        list, list[FilteredActivity]]:
        """
        同步方式过滤活动（用于已知集合的场景）

        Args:
            activities: 活动对象列表（需要有 id 属性）
            ignored_ids: 被忽略的活动ID集合
            interested_ids: 感兴趣的活动ID集合（可选）

        Returns:
            (保留的活动列表, 被过滤掉的 FilteredActivity 列表)
        """
        if not activities:
            return [], []

        interested_ids = interested_ids or set()

        kept = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None and isinstance(activity, dict):
                activity_id = activity.get('id')

            # 感兴趣白名单优先
            if activity_id and activity_id in interested_ids:
                kept.append(activity)
                continue

            if activity_id and activity_id in ignored_ids:
                filtered.append(FilteredActivity(
                    activity=activity,
                    reason="用户已标记为不感兴趣",
                    filter_type="ignore"
                ))
            else:
                kept.append(activity)

        return kept, filtered

    async def restore_interested_activities(self, activities: list) -> tuple[list, list]:
        """
        从活动列表中识别并恢复感兴趣的活动

        用于新活动通知场景：将已在 interested 列表中的活动标记为恢复，
        这些活动将绕过后续的 AI/时间筛选。

        Args:
            activities: 待检查的活动列表

        Returns:
            (需要进一步筛选的活动列表, 已恢复的活动列表)
        """
        if not activities:
            return [], []

        interested_ids = await self.get_all_interested_ids()

        if not interested_ids:
            return activities, []

        to_filter = []  # 需要进一步筛选的活动
        restored = []  # 已恢复的活动（在白名单中）

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None and isinstance(activity, dict):
                activity_id = activity.get('id')

            if activity_id and activity_id in interested_ids:
                restored.append(activity)
                logger.debug(f"活动 {activity_id} 在感兴趣白名单中，将绕过筛选")
            else:
                to_filter.append(activity)

        if restored:
            logger.info(f"从感兴趣白名单恢复了 {len(restored)} 个活动，将绕过 AI/时间筛选")

        return to_filter, restored
