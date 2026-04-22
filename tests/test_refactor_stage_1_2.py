"""阶段 1/2 重构回归测试。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pyustc.young import Status

from src.core.repositories import ActivityRepository
from src.core.secondclass_db import SecondClassDB
from src.core.user_preference_manager import UserPreferenceManager
from src.models.activity import (
    format_secondclass_for_list,
    get_participation_form,
    secondclass_from_db_row,
)


def _activity_row(
    activity_id: str = "a1",
    name: str = "测试活动",
    status: int = Status.APPLYING.code,
    place_info: str | None = "西区活动室",
    participation_form: str | None = "0",
    hold_time: dict | None = None,
) -> dict:
    return {
        "id": activity_id,
        "name": name,
        "status": status,
        "create_time": None,
        "apply_time": None,
        "hold_time": json.dumps(hold_time) if hold_time else None,
        "tel": "",
        "valid_hour": 1.0,
        "apply_num": 1,
        "apply_limit": 10,
        "applied": 0,
        "need_sign_info": 0,
        "module": None,
        "department": None,
        "labels": None,
        "conceive": "",
        "is_series": 0,
        "place_info": place_info,
        "children_id": None,
        "parent_id": None,
        "scan_timestamp": 123,
        "deep_scaned": 0,
        "deep_scaned_time": None,
        "participation_form": participation_form,
    }


def _insert_row(db_path: Path, table: str, row: dict) -> None:
    columns = list(row.keys())
    placeholders = ",".join(["?"] * len(columns))
    column_sql = ",".join(columns)
    values = [row[column] for column in columns]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
            values,
        )
        conn.commit()


class ActivityMapperFormatterTest(unittest.TestCase):
    def test_place_and_participation_form_are_restored_from_db_row(self) -> None:
        activity = secondclass_from_db_row(_activity_row())

        self.assertEqual(activity.place_info, "西区活动室")
        self.assertEqual(get_participation_form(activity), "现场参与")

        text = format_secondclass_for_list(activity, 1)
        self.assertIn("地点：西区活动室", text)
        self.assertIn("参与形式：现场参与", text)

    def test_missing_place_and_participation_form_use_fallbacks(self) -> None:
        activity = secondclass_from_db_row(
            _activity_row(activity_id="a2", place_info=None, participation_form=None)
        )

        text = format_secondclass_for_list(activity, 1)
        self.assertIn("地点：未提供", text)
        self.assertNotIn("参与形式：", text)


class ActivityRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_by_ids_preserves_input_order_and_skips_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, "all_secondclass", _activity_row("a", "Alpha"))
            _insert_row(db_path, "all_secondclass", _activity_row("b", "Beta"))

            repo = ActivityRepository()
            activities = await repo.get_by_ids(db_path, ["b", "missing", "a"])

            self.assertEqual([activity.id for activity in activities], ["b", "a"])

    async def test_enrolled_time_ranges_skip_submit_works_and_old_records(self) -> None:
        now = datetime.now()
        future_range = {
            "start": (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (now + timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        old_range = {
            "start": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (now - timedelta(days=3, hours=-2)).strftime("%Y-%m-%d %H:%M:%S"),
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(
                db_path,
                "enrolled_secondclass",
                _activity_row("future", "未来活动", hold_time=future_range, participation_form=None),
            )
            _insert_row(
                db_path,
                "enrolled_secondclass",
                _activity_row("works", "提交作品", hold_time=future_range, participation_form="1"),
            )
            _insert_row(
                db_path,
                "enrolled_secondclass",
                _activity_row("old", "过期活动", hold_time=old_range, participation_form=None),
            )

            ranges = await ActivityRepository().list_enrolled_time_ranges(db_path)

            self.assertEqual([time_range.name for time_range in ranges], ["未来活动"])


class UserPreferenceManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_single_and_batch_preferences_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = UserPreferenceManager(Path(tmp_dir) / "preference.db")
            await manager.initialize()

            self.assertTrue(await manager.add_interested_activity("a"))
            self.assertTrue(await manager.add_ignored_activity("a"))
            self.assertTrue(await manager.is_ignored("a"))
            self.assertFalse(await manager.is_interested("a"))

            self.assertEqual(await manager.add_interested_activities(["a", "b"]), (2, 0))
            self.assertEqual(await manager.get_all_interested_ids(), {"a", "b"})
            self.assertEqual(await manager.get_all_ignored_ids(), set())

            self.assertEqual(await manager.add_ignored_activities(["b", "c"]), (2, 0))
            self.assertEqual(await manager.get_all_interested_ids(), {"a"})
            self.assertEqual(await manager.get_all_ignored_ids(), {"b", "c"})


if __name__ == "__main__":
    unittest.main()
