"""用户偏好数据库管理器"""

import time
from pathlib import Path
from typing import Optional

import aiosqlite

from src.core.repositories import ActivityRepository, PreferenceKind, PreferenceRepository
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("user_preference_manager")


class UserPreferenceManager:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            project_root = Path(__file__).parent.parent.parent
            db_path = project_root / "data" / "user_preference.db"
        else:
            db_path = Path(db_path)
            if not db_path.is_absolute():
                project_root = Path(__file__).parent.parent.parent
                db_path = project_root / db_path

        self.db_path = db_path.resolve()
        self.preference_repository = PreferenceRepository(self.db_path)
        self.activity_repository = ActivityRepository()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        await self._migrate_from_old_db()

        await self.preference_repository.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_filter_result (
                    activity_id TEXT PRIMARY KEY,
                    reviewed_at INTEGER NOT NULL,
                    is_interested BOOLEAN NOT NULL,
                    reason TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_filter_reviewed_at 
                ON ai_filter_result(reviewed_at)
            """)

            await db.commit()

        self._initialized = True
        logger.info(f"用户偏好数据库初始化完成: {self.db_path}")

    async def _migrate_from_old_db(self) -> None:
        old_db_path = self.db_path.parent / "ignore.db"

        if not old_db_path.exists():
            return

        if self.db_path.exists():
            logger.info("新数据库已存在，跳过数据迁移")
            try:
                old_db_path.unlink()
                logger.info(f"已删除旧数据库: {old_db_path}")
            except OSError as e:
                logger.warning(f"删除旧数据库失败: {e}")
            return

        logger.info(f"检测到旧数据库，开始迁移: {old_db_path}")

        try:
            async with aiosqlite.connect(self.db_path) as new_db:
                await new_db.execute("""
                    CREATE TABLE IF NOT EXISTS ignored_activities (
                        activity_id TEXT PRIMARY KEY,
                        added_at INTEGER NOT NULL
                    )
                """)

                async with aiosqlite.connect(old_db_path) as old_db:
                    async with old_db.execute(
                            "SELECT activity_id, added_at FROM ignored_activities"
                    ) as cursor:
                        rows = await cursor.fetchall()

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

            try:
                old_db_path.unlink()
                logger.info(f"已删除旧数据库: {old_db_path}")
            except OSError as e:
                logger.warning(f"删除旧数据库失败: {e}")

        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            if self.db_path.exists():
                try:
                    self.db_path.unlink()
                except OSError:
                    pass
            raise

    async def add_ignored_activity(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            _, failed_count = await self.preference_repository.add_many(
                PreferenceKind.IGNORED,
                [activity_id],
            )

            logger.debug(f"添加活动到忽略列表: {activity_id}")
            return failed_count == 0

        except Exception as e:
            logger.error(f"添加活动到忽略列表失败: {e}")
            return False

    async def add_ignored_activities(self, activity_ids: list[str]) -> tuple[int, int]:
        await self.initialize()

        if not activity_ids:
            return 0, 0

        try:
            success_count, failed_count = await self.preference_repository.add_many(
                PreferenceKind.IGNORED,
                activity_ids,
            )

            logger.info(f"批量添加忽略活动: 成功 {success_count} 个, 失败 {failed_count} 个")
            return success_count, failed_count

        except Exception as e:
            logger.error(f"批量添加忽略活动失败: {e}")
            return 0, len(activity_ids)

    async def is_ignored(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            return await self.preference_repository.exists(PreferenceKind.IGNORED, activity_id)

        except Exception as e:
            logger.error(f"检查活动忽略状态失败: {e}")
            return False

    async def get_all_ignored_ids(self) -> set[str]:
        await self.initialize()

        try:
            return await self.preference_repository.get_ids(PreferenceKind.IGNORED)

        except Exception as e:
            logger.error(f"获取忽略活动列表失败: {e}")
            return set()

    async def remove_ignored_activity(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            await self.preference_repository.remove_many(PreferenceKind.IGNORED, [activity_id])

            logger.debug(f"从忽略列表移除活动: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"从忽略列表移除活动失败: {e}")
            return False

    async def toggle_ignored_activity(self, activity_id: str) -> tuple[bool, bool]:
        await self.initialize()

        try:
            is_currently_ignored = await self.is_ignored(activity_id)

            if is_currently_ignored:
                success = await self.remove_ignored_activity(activity_id)
                return success, False
            else:
                success = await self.add_ignored_activity(activity_id)
                return success, True

        except Exception as e:
            logger.error(f"切换活动不感兴趣状态失败: {e}")
            try:
                original_state = await self.is_ignored(activity_id)
                return False, original_state
            except Exception as fallback_error:
                logger.error(f"读取活动不感兴趣原始状态失败: {fallback_error}")
                return False, False

    async def toggle_interested_activity(self, activity_id: str) -> tuple[bool, bool]:
        await self.initialize()

        try:
            is_currently_interested = await self.is_interested(activity_id)

            if is_currently_interested:
                success = await self.remove_interested_activity(activity_id)
                return success, False
            else:
                success = await self.add_interested_activity(activity_id)
                return success, True

        except Exception as e:
            logger.error(f"切换活动感兴趣状态失败: {e}")
            try:
                original_state = await self.is_interested(activity_id)
                return False, original_state
            except Exception as fallback_error:
                logger.error(f"读取活动感兴趣原始状态失败: {fallback_error}")
                return False, False

    async def get_ignored_count(self) -> int:
        await self.initialize()

        try:
            return await self.preference_repository.count(PreferenceKind.IGNORED)

        except Exception as e:
            logger.error(f"获取忽略活动数量失败: {e}")
            return 0

    def get_ignored_count_sync(self) -> int:
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

    async def add_interested_activity(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            _, failed_count = await self.preference_repository.add_many(
                PreferenceKind.INTERESTED,
                [activity_id],
            )

            logger.debug(f"添加活动到感兴趣列表: {activity_id}")
            return failed_count == 0

        except Exception as e:
            logger.error(f"添加活动到感兴趣列表失败: {e}")
            return False

    async def add_interested_activities(self, activity_ids: list[str]) -> tuple[int, int]:
        await self.initialize()

        if not activity_ids:
            return 0, 0

        try:
            success_count, failed_count = await self.preference_repository.add_many(
                PreferenceKind.INTERESTED,
                activity_ids,
            )

            logger.info(f"批量添加感兴趣活动: 成功 {success_count} 个, 失败 {failed_count} 个")
            return success_count, failed_count

        except Exception as e:
            logger.error(f"批量添加感兴趣活动失败: {e}")
            return 0, len(activity_ids)

    async def is_interested(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            return await self.preference_repository.exists(PreferenceKind.INTERESTED, activity_id)

        except Exception as e:
            logger.error(f"检查活动感兴趣状态失败: {e}")
            return False

    async def get_all_interested_ids(self) -> set[str]:
        await self.initialize()

        try:
            return await self.preference_repository.get_ids(PreferenceKind.INTERESTED)

        except Exception as e:
            logger.error(f"获取感兴趣活动列表失败: {e}")
            return set()

    async def get_preference_activities(self, latest_db: Path, preference_type: str) -> list:
        """从最新活动数据库中查询已标记的活动。"""
        await self.initialize()

        if preference_type == "interested":
            activity_ids = await self.get_all_interested_ids()
        elif preference_type == "ignored":
            activity_ids = await self.get_all_ignored_ids()
        else:
            raise ValueError(f"未知偏好类型: {preference_type}")

        if not activity_ids:
            return []

        try:
            return await self.activity_repository.get_by_ids(latest_db, list(activity_ids))
        except Exception as e:
            logger.error(f"查询 {preference_type} 活动列表失败: {e}")
            return []

    async def remove_interested_activity(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            await self.preference_repository.remove_many(PreferenceKind.INTERESTED, [activity_id])

            logger.debug(f"从感兴趣列表移除活动: {activity_id}")
            return True

        except Exception as e:
            logger.error(f"从感兴趣列表移除活动失败: {e}")
            return False

    async def get_interested_count(self) -> int:
        await self.initialize()

        try:
            return await self.preference_repository.count(PreferenceKind.INTERESTED)

        except Exception as e:
            logger.error(f"获取感兴趣活动数量失败: {e}")
            return 0

    def get_interested_count_sync(self) -> int:
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

    async def filter_activities(self, activities: list) -> tuple[list, list[FilteredActivity]]:
        if not activities:
            return [], []

        interested_ids = await self.get_all_interested_ids()
        ignored_ids = await self.get_all_ignored_ids()

        kept = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None:
                if isinstance(activity, dict):
                    activity_id = activity.get('id')

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
        if not activities:
            return [], []

        interested_ids = interested_ids or set()

        kept = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None and isinstance(activity, dict):
                activity_id = activity.get('id')

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
        if not activities:
            return [], []

        interested_ids = await self.get_all_interested_ids()

        if not interested_ids:
            return activities, []

        to_filter = []
        restored = []

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

    async def get_ai_filter_result(self, activity_id: str) -> Optional[dict]:
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT is_interested, reason, reviewed_at FROM ai_filter_result WHERE activity_id = ?",
                        (activity_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "is_interested": bool(row[0]),
                            "reason": row[1],
                            "reviewed_at": row[2]
                        }
                    return None
        except Exception as e:
            logger.error(f"获取 AI 筛选结果失败: {e}")
            return None

    async def get_ai_filter_results(self, activity_ids: list[str]) -> dict[str, dict]:
        await self.initialize()

        if not activity_ids:
            return {}

        try:
            placeholders = ','.join('?' * len(activity_ids))
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        f"SELECT activity_id, is_interested, reason, reviewed_at FROM ai_filter_result WHERE activity_id IN ({placeholders})",
                        activity_ids
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {
                        row[0]: {
                            "is_interested": bool(row[1]),
                            "reason": row[2],
                            "reviewed_at": row[3]
                        }
                        for row in rows
                    }
        except Exception as e:
            logger.error(f"批量获取 AI 筛选结果失败: {e}")
            return {}

    async def save_ai_filter_result(
            self,
            activity_id: str,
            is_interested: bool,
            reason: str,
            reviewed_at: Optional[int] = None
    ) -> bool:
        await self.initialize()

        if reviewed_at is None:
            reviewed_at = int(time.time())

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO ai_filter_result (activity_id, reviewed_at, is_interested, reason)
                    VALUES (?, ?, ?, ?)
                    """,
                    (activity_id, reviewed_at, int(is_interested), reason)
                )
                await db.commit()
            logger.debug(f"保存 AI 筛选结果: {activity_id}, interested={is_interested}")
            return True
        except Exception as e:
            logger.error(f"保存 AI 筛选结果失败: {e}")
            return False

    async def save_ai_filter_results(
            self,
            results: list[tuple[str, bool, str, Optional[int]]]
    ) -> tuple[int, int]:
        await self.initialize()

        if not results:
            return 0, 0

        success_count = 0
        failed_count = 0
        current_time = int(time.time())

        try:
            async with aiosqlite.connect(self.db_path) as db:
                for result in results:
                    try:
                        activity_id, is_interested, reason, reviewed_at = result
                        if reviewed_at is None:
                            reviewed_at = current_time

                        await db.execute(
                            """
                            INSERT OR REPLACE INTO ai_filter_result (activity_id, reviewed_at, is_interested, reason)
                            VALUES (?, ?, ?, ?)
                            """,
                            (activity_id, reviewed_at, int(is_interested), reason)
                        )
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"保存活动 {result[0] if result else 'unknown'} 的 AI 筛选结果失败: {e}")
                        failed_count += 1

                await db.commit()

            logger.info(f"批量保存 AI 筛选结果: 成功 {success_count} 个, 失败 {failed_count} 个")
            return success_count, failed_count
        except Exception as e:
            logger.error(f"批量保存 AI 筛选结果失败: {e}")
            return 0, len(results)

    async def delete_ai_filter_result(self, activity_id: str) -> bool:
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM ai_filter_result WHERE activity_id = ?",
                    (activity_id,)
                )
                await db.commit()
            logger.debug(f"删除 AI 筛选结果: {activity_id}")
            return True
        except Exception as e:
            logger.error(f"删除 AI 筛选结果失败: {e}")
            return False

    async def get_all_ai_filter_results(self) -> dict[str, dict]:
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT activity_id, is_interested, reason, reviewed_at FROM ai_filter_result"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {
                        row[0]: {
                            "is_interested": bool(row[1]),
                            "reason": row[2],
                            "reviewed_at": row[3]
                        }
                        for row in rows
                    }
        except Exception as e:
            logger.error(f"获取所有 AI 筛选结果失败: {e}")
            return {}

    async def clear_ai_filter_results(self) -> bool:
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM ai_filter_result")
                await db.commit()
            logger.info("已清空所有 AI 筛选结果")
            return True
        except Exception as e:
            logger.error(f"清空 AI 筛选结果失败: {e}")
            return False

    async def get_ai_filter_count(self) -> int:
        await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                        "SELECT COUNT(*) FROM ai_filter_result"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"获取 AI 筛选结果数量失败: {e}")
            return 0
