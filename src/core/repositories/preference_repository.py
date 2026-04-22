"""用户偏好数据库基础 CRUD。"""

import time
from enum import Enum
from pathlib import Path

import aiosqlite

from src.utils.logger import get_logger

logger = get_logger("repository.preference")


class PreferenceKind(str, Enum):
    """可持久化的用户偏好类型。"""

    IGNORED = "ignored"
    INTERESTED = "interested"


class PreferenceRepository:
    """封装用户偏好表访问，不接受外部表名。"""

    _TABLES = {
        PreferenceKind.IGNORED: "ignored_activities",
        PreferenceKind.INTERESTED: "interested_activities",
    }
    _OPPOSITE = {
        PreferenceKind.IGNORED: PreferenceKind.INTERESTED,
        PreferenceKind.INTERESTED: PreferenceKind.IGNORED,
    }

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT OR IGNORE INTO meta (key, value)
                VALUES ('schema_version', '1')
            """)
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

    async def get_ids(self, kind: PreferenceKind) -> set[str]:
        table = self._table(kind)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(f"SELECT activity_id FROM {table}") as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}

    async def exists(self, kind: PreferenceKind, activity_id: str) -> bool:
        table = self._table(kind)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT 1 FROM {table} WHERE activity_id = ?",
                (activity_id,),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def add_many(self, kind: PreferenceKind, activity_ids: list[str]) -> tuple[int, int]:
        if not activity_ids:
            return 0, 0

        table = self._table(kind)
        opposite_table = self._table(self._OPPOSITE[kind])
        unique_ids = list(dict.fromkeys(activity_ids))
        placeholders = ",".join(["?"] * len(unique_ids))
        now = int(time.time())
        rows = [(activity_id, now) for activity_id in unique_ids]

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("BEGIN")
                await db.execute(
                    f"DELETE FROM {opposite_table} WHERE activity_id IN ({placeholders})",
                    unique_ids,
                )
                await db.executemany(
                    f"""
                    INSERT OR REPLACE INTO {table} (activity_id, added_at)
                    VALUES (?, ?)
                    """,
                    rows,
                )
                await db.commit()
            return len(activity_ids), 0
        except Exception as e:
            logger.error(f"批量写入偏好失败 kind={kind.value}: {e}")
            return 0, len(activity_ids)

    async def remove_many(self, kind: PreferenceKind, activity_ids: list[str]) -> int:
        if not activity_ids:
            return 0

        table = self._table(kind)
        unique_ids = list(dict.fromkeys(activity_ids))
        placeholders = ",".join(["?"] * len(unique_ids))

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"DELETE FROM {table} WHERE activity_id IN ({placeholders})",
                unique_ids,
            )
            await db.commit()
            return cursor.rowcount if cursor.rowcount is not None else 0

    async def count(self, kind: PreferenceKind) -> int:
        table = self._table(kind)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    @classmethod
    def _table(cls, kind: PreferenceKind) -> str:
        try:
            return cls._TABLES[kind]
        except KeyError as e:
            raise ValueError(f"未知偏好类型: {kind}") from e
