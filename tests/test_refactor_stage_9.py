"""阶段 9 搜索与索引优化回归测试。"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pyustc.young import SecondClass, Status

from src.core.repositories import ActivityRepository
from src.core.search_index import FTS_TABLE, supports_trigram_fts5
from src.core.secondclass_db import SecondClassDB


def _clear_secondclass_cache(activity_id: str) -> None:
    SecondClass._instance_cache.pop(activity_id, None)


def _activity_row(
    activity_id: str,
    name: str,
    department: str | None = None,
    labels: str | None = None,
    conceive: str = "",
    place_info: str | None = "西区活动室",
) -> dict:
    return {
        "id": activity_id,
        "name": name,
        "status": Status.APPLYING.code,
        "create_time": None,
        "apply_time": None,
        "hold_time": None,
        "tel": "",
        "valid_hour": 1.0,
        "apply_num": 1,
        "apply_limit": 10,
        "applied": 0,
        "need_sign_info": 0,
        "module": None,
        "department": department,
        "labels": labels,
        "conceive": conceive,
        "is_series": 0,
        "place_info": place_info,
        "children_id": None,
        "parent_id": None,
        "scan_timestamp": 123,
        "deep_scaned": 0,
        "deep_scaned_time": None,
        "participation_form": "0",
    }


def _insert_row(db_path: Path, row: dict) -> None:
    columns = list(row.keys())
    placeholders = ",".join(["?"] * len(columns))
    column_sql = ",".join(columns)
    values = [row[column] for column in columns]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO all_secondclass ({column_sql}) VALUES ({placeholders})",
            values,
        )
        conn.commit()


def _sqlite_supports_trigram_fts() -> bool:
    with sqlite3.connect(":memory:") as conn:
        return supports_trigram_fts5(conn)


def _sample_secondclass(activity_id: str, name: str, conceive: str) -> SecondClass:
    _clear_secondclass_cache(activity_id)
    return SecondClass.from_dict(
        {
            "id": activity_id,
            "itemName": name,
            "itemStatus": Status.APPLYING.code,
            "applySt": "2026-04-24 10:00:00",
            "applyEt": "2026-04-25 10:00:00",
            "st": "2026-04-26 14:00:00",
            "et": "2026-04-26 16:00:00",
            "tel": "123456",
            "validHour": 2.0,
            "applyNum": 1,
            "peopleNum": 20,
            "booleanRegistration": "0",
            "needSignInfo": "0",
            "module": "m1",
            "moduleName": "文化素质",
            "businessDeptId": "d1",
            "bussinessDeptName": "校团委",
            "itemLable": "l1",
            "lableNames": "讲座",
            "conceive": conceive,
            "baseContent": "活动描述",
            "itemCategory": "0",
            "placeInfo": "西区活动室",
            "form": "0",
        }
    )


class ActivitySearchIndexTest(unittest.IsolatedAsyncioTestCase):
    async def test_base_indexes_are_created_for_all_secondclass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)

            with sqlite3.connect(db_path) as conn:
                indexes = {row[1] for row in conn.execute("PRAGMA index_list(all_secondclass)")}

            self.assertIn("idx_all_secondclass_status", indexes)
            self.assertIn("idx_all_secondclass_name", indexes)
            self.assertIn("idx_all_secondclass_scan_timestamp", indexes)
            self.assertIn("idx_all_secondclass_parent_id", indexes)

    async def test_default_search_keeps_chinese_name_like_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, _activity_row("title-a", "人工智能讲座"))
            _insert_row(db_path, _activity_row("title-b", "智能硬件沙龙"))
            _insert_row(db_path, _activity_row("conceive-only", "普通分享", conceive="人工智能项目体验"))

            repo = ActivityRepository()
            default_result = await repo.search(db_path, "智能")
            legacy_result = await repo.search_by_name(db_path, "智能")

            self.assertEqual(
                {activity.id for activity in default_result},
                {activity.id for activity in legacy_result},
            )
            self.assertEqual(
                {activity.id for activity in default_result},
                {"title-a", "title-b"},
            )

    async def test_full_text_search_auto_creates_fts_and_expands_fields(self) -> None:
        if not _sqlite_supports_trigram_fts():
            self.skipTest("SQLite FTS5 trigram tokenizer is unavailable")

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, _activity_row("title-ai", "人工智能讲座"))
            _insert_row(db_path, _activity_row("conceive-ai", "普通分享", conceive="人工智能项目体验"))
            _insert_row(
                db_path,
                _activity_row(
                    "department-ai",
                    "学院活动",
                    department=json.dumps({"id": "d1", "name": "人工智能学院"}, ensure_ascii=False),
                ),
            )
            _insert_row(
                db_path,
                _activity_row(
                    "label-ai",
                    "标签活动",
                    labels=json.dumps([{"id": "l1", "name": "人工智能"}], ensure_ascii=False),
                ),
            )
            _insert_row(db_path, _activity_row("place-ai", "地点活动", place_info="人工智能实验室"))

            with sqlite3.connect(db_path) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")
                conn.commit()

            repo = ActivityRepository(search_mode="full_text")
            activities = await repo.search(db_path, "人工智能")

            self.assertEqual(
                {activity.id for activity in activities},
                {"title-ai", "conceive-ai", "department-ai", "label-ai", "place-ai"},
            )
            with sqlite3.connect(db_path) as conn:
                fts_table = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (FTS_TABLE,),
                ).fetchone()
            self.assertIsNotNone(fts_table)

    async def test_full_text_short_keyword_falls_back_to_name_like(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, _activity_row("title-a", "人工智能讲座"))
            _insert_row(db_path, _activity_row("conceive-only", "普通分享", conceive="智能项目体验"))

            repo = ActivityRepository(search_mode="full_text")
            activities = await repo.search(db_path, "智能")

            self.assertEqual([activity.id for activity in activities], ["title-a"])

    async def test_snapshot_write_rebuilds_full_text_index(self) -> None:
        if not _sqlite_supports_trigram_fts():
            self.skipTest("SQLite FTS5 trigram tokenizer is unavailable")

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            db = SecondClassDB(db_path)
            await db.update_all_secondclass(
                [_sample_secondclass("sync-ai", "同步活动", "人工智能活动构想")],
                deep_update=False,
            )

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    f"""
                    SELECT a.id
                    FROM {FTS_TABLE} f
                    JOIN all_secondclass a ON a.id = f.id
                    WHERE {FTS_TABLE} MATCH ?
                    """,
                    ("人工智能",),
                ).fetchall()

            self.assertEqual([row[0] for row in rows], ["sync-ai"])


if __name__ == "__main__":
    unittest.main()
