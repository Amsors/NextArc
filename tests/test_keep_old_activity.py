"""旧活动保留扫描逻辑回归测试。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pyustc.young import Status

from src.config.settings import MonitorConfig
from src.core.repositories import ActivityRepository
from src.core.scanning.coordinator import ScanCoordinator
from src.core.secondclass_db import SecondClassDB
from src.core.services.activity_update_service import ActivityUpdateResult


def _activity_row(activity_id: str, name: str, end_time: datetime) -> dict:
    start_time = end_time - timedelta(hours=2)
    hold_time = {
        "start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {
        "id": activity_id,
        "name": name,
        "status": Status.APPLYING.code,
        "create_time": None,
        "apply_time": None,
        "hold_time": json.dumps(hold_time),
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
        "place_info": None,
        "children_id": None,
        "parent_id": None,
        "scan_timestamp": 100,
        "deep_scaned": 0,
        "deep_scaned_time": None,
        "participation_form": None,
    }


def _insert_row(db_path: Path, row: dict) -> None:
    columns = list(row.keys())
    placeholders = ",".join(["?"] * len(columns))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO all_secondclass ({','.join(columns)}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )
        conn.commit()


class FakeActivityUpdateService:
    def __init__(self) -> None:
        self.updated_ids: list[str] = []

    async def update_activities(
        self,
        activities,
        max_concurrent=None,
        continue_on_error: bool = True,
    ) -> ActivityUpdateResult:
        self.updated_ids = [activity.id for activity in activities]
        return ActivityUpdateResult(successful=activities, failed=[])


class KeepOldActivityTest(unittest.IsolatedAsyncioTestCase):
    async def test_keep_old_unended_activity_updates_missing_old_rows_and_appends_future_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_db = Path(tmp_dir) / "old.db"
            new_db = Path(tmp_dir) / "new.db"
            SecondClassDB(old_db)
            SecondClassDB(new_db)

            now = datetime.now()
            _insert_row(old_db, _activity_row("current", "本次仍存在活动", now + timedelta(days=3)))
            _insert_row(old_db, _activity_row("future-old", "仍未结束旧活动", now + timedelta(days=2)))
            _insert_row(old_db, _activity_row("ended-old", "已结束旧活动", now - timedelta(days=1)))
            _insert_row(new_db, _activity_row("current", "本次仍存在活动", now + timedelta(days=3)))

            update_service = FakeActivityUpdateService()
            repository = ActivityRepository()
            coordinator = ScanCoordinator(
                db_manager=object(),
                sync_service=object(),
                diff_service=object(),
                filter_pipeline=object(),
                activity_update_service=update_service,
                activity_repository=repository,
            )

            kept_count = await coordinator._keep_old_unended_activities(old_db, new_db)
            rows = await repository.list_all_rows(new_db)

            self.assertEqual(kept_count, 1)
            self.assertEqual(update_service.updated_ids, ["future-old", "ended-old"])
            self.assertIn("current", rows)
            self.assertIn("future-old", rows)
            self.assertNotIn("ended-old", rows)

    def test_keep_old_activity_defaults_to_enabled(self) -> None:
        self.assertTrue(MonitorConfig().keep_old_activity)

    def test_add_sub_secondclass_into_db_defaults_to_disabled(self) -> None:
        self.assertFalse(MonitorConfig().add_sub_secondclass_into_db)


if __name__ == "__main__":
    unittest.main()
