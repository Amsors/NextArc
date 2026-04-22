"""活动快照数据库只读查询。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
from pyustc.young import SecondClass, Status

from src.core.overlay_filter import EnrolledActivityTime
from src.models.activity import secondclass_from_db_row
from src.utils.logger import get_logger

logger = get_logger("repository.activity")


class ActivityRepository:
    """集中封装活动快照 SQLite 查询。"""

    async def count_all(self, db_path: Path) -> int:
        return await self._count(db_path, "all_secondclass")

    async def count_enrolled(self, db_path: Path) -> int:
        return await self._count(db_path, "enrolled_secondclass")

    async def list_all(self, db_path: Path) -> list[SecondClass]:
        return await self._list_from_table(db_path, "all_secondclass", "ORDER BY name")

    async def list_valid(self, db_path: Path) -> list[SecondClass]:
        valid_status_codes = [Status.APPLYING.code, Status.PUBLISHED.code]
        placeholders = ",".join(["?"] * len(valid_status_codes))
        query = f"""
            SELECT * FROM all_secondclass
            WHERE status IN ({placeholders})
            ORDER BY name
        """
        return await self._query_activities(db_path, query, valid_status_codes)

    async def search_by_name(self, db_path: Path, keyword: str) -> list[SecondClass]:
        keyword_lower = keyword.lower()
        query = "SELECT * FROM all_secondclass WHERE LOWER(name) LIKE ? ORDER BY name"
        activities = await self._query_activities(db_path, query, [f"%{keyword_lower}%"])
        logger.debug(f"搜索关键词 {keyword_lower!r} 命中 {len(activities)} 个活动")
        return activities

    async def get_by_ids(self, db_path: Path, activity_ids: list[str]) -> list[SecondClass]:
        if not activity_ids:
            return []

        unique_ids = list(dict.fromkeys(activity_ids))
        placeholders = ",".join(["?"] * len(unique_ids))
        query = f"SELECT * FROM all_secondclass WHERE id IN ({placeholders})"
        activities = await self._query_activities(db_path, query, unique_ids)
        activity_map = {activity.id: activity for activity in activities}
        return [activity_map[activity_id] for activity_id in activity_ids if activity_id in activity_map]

    async def list_enrolled(self, db_path: Path) -> list[SecondClass]:
        return await self._list_from_table(db_path, "enrolled_secondclass", "ORDER BY name")

    async def list_enrolled_ids(self, db_path: Path) -> set[str]:
        if not db_path.exists():
            return set()

        enrolled_ids: set[str] = set()
        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute("SELECT id FROM enrolled_secondclass") as cursor:
                    async for row in cursor:
                        enrolled_ids.add(row[0])
        except Exception as e:
            logger.error(f"加载已报名活动 ID 失败 {db_path}: {e}")
            return set()

        logger.debug(f"已报名活动数量: {len(enrolled_ids)}")
        return enrolled_ids

    async def list_enrolled_time_ranges(self, db_path: Path) -> list[EnrolledActivityTime]:
        if not db_path.exists():
            return []

        time_ranges: list[EnrolledActivityTime] = []
        now = datetime.now()

        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    """
                    SELECT hold_time, name, participation_form
                    FROM enrolled_secondclass
                    WHERE participation_form IS NULL
                       OR CAST(participation_form AS INTEGER) != 1
                    """
                ) as cursor:
                    async for row in cursor:
                        hold_time_json = row[0]
                        activity_name = row[1] or "未知活动"
                        if not hold_time_json:
                            continue

                        time_range = self._parse_enrolled_time_range(
                            hold_time_json=hold_time_json,
                            activity_name=activity_name,
                            now=now,
                        )
                        if time_range:
                            time_ranges.append(time_range)
        except Exception as e:
            logger.error(f"获取已报名活动时间列表失败: {e}")
            return []

        logger.debug(f"从数据库获取到 {len(time_ranges)} 个有效已报名活动时间（已排除提交作品类活动）")
        return time_ranges

    async def get_scan_time(self, db_path: Path) -> datetime | None:
        if not db_path.exists():
            return None

        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT MIN(scan_timestamp) FROM all_secondclass"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return datetime.fromtimestamp(row[0])
        except Exception as e:
            logger.warning(f"获取数据库扫描时间失败 {db_path}: {e}")

        return None

    async def _count(self, db_path: Path, table: str) -> int:
        if table not in {"all_secondclass", "enrolled_secondclass"}:
            raise ValueError(f"Invalid activity table: {table}")
        if not db_path.exists():
            return 0

        async with aiosqlite.connect(db_path) as db:
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def _list_from_table(self, db_path: Path, table: str, suffix: str = "") -> list[SecondClass]:
        if table not in {"all_secondclass", "enrolled_secondclass"}:
            raise ValueError(f"Invalid activity table: {table}")
        return await self._query_activities(db_path, f"SELECT * FROM {table} {suffix}".strip(), [])

    async def _query_activities(
        self,
        db_path: Path,
        query: str,
        params: list[str | int | float],
    ) -> list[SecondClass]:
        if not db_path.exists():
            logger.warning(f"数据库不存在: {db_path}")
            return []

        activities: list[SecondClass] = []
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    activities.append(secondclass_from_db_row(dict(row)))
        return activities

    @staticmethod
    def _parse_enrolled_time_range(
        hold_time_json: str,
        activity_name: str,
        now: datetime,
    ) -> EnrolledActivityTime | None:
        try:
            data = json.loads(hold_time_json)
            if not isinstance(data, dict):
                logger.warning(f"已报名活动时间格式异常（期望字典）: {hold_time_json}")
                return None

            start_str = data.get("start")
            end_str = data.get("end")
            start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S") if start_str else None
            end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S") if end_str else None
            if not start_dt:
                return None

            effective_end = end_dt or (start_dt + timedelta(hours=2))
            if effective_end < now - timedelta(days=1):
                return None

            return EnrolledActivityTime(start=start_dt, end=end_dt, name=activity_name)
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"解析已报名活动时间失败: {e}, 数据={hold_time_json}")
            return None
