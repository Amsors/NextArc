"""报名成功后的已报名快照增量维护测试。"""

import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pyustc.young import SecondClass, Status

from src.core.repositories import ActivityRepository
from src.core.secondclass_db import SecondClassDB
from src.core.services import EnrollmentService


def _clear_secondclass_cache(activity_id: str) -> None:
    SecondClass._instance_cache.pop(activity_id, None)


def _sample_secondclass(activity_id: str = "enroll-snapshot") -> SecondClass:
    _clear_secondclass_cache(activity_id)
    return SecondClass.from_dict(
        {
            "id": activity_id,
            "itemName": "报名快照活动",
            "itemStatus": Status.APPLYING.code,
            "createTime": "2026-04-24 09:00:00",
            "applySt": "2026-04-24 10:00:00",
            "applyEt": "2026-04-25 10:00:00",
            "st": "2026-04-26 14:00:00",
            "et": "2026-04-26 16:00:00",
            "tel": "123456",
            "validHour": 2.0,
            "applyNum": 3,
            "peopleNum": 20,
            "booleanRegistration": 0,
            "needSignInfo": "0",
            "module": "m1",
            "moduleName": "文化素质",
            "businessDeptId": "d1",
            "bussinessDeptName": "校团委",
            "itemLable": "l1",
            "lableNames": "讲座",
            "conceive": "活动构想",
            "itemCategory": "0",
            "placeInfo": "西区活动室",
            "form": "0",
        }
    )


class FakeAuthManager:
    @asynccontextmanager
    async def create_session_once(self):
        yield


class FakeDBManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_latest_db(self) -> Path:
        return self.db_path


class EnrollmentSnapshotTest(unittest.IsolatedAsyncioTestCase):
    async def test_join_success_upserts_latest_enrolled_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            activity = _sample_secondclass("join-snapshot")
            activity.update = AsyncMock()
            activity.apply = AsyncMock(return_value=True)

            service = EnrollmentService(
                auth_manager=FakeAuthManager(),
                calendar_sync_enabled=False,
                db_manager=FakeDBManager(db_path),
            )

            with patch("src.core.services.enrollment_service.SecondClass", return_value=activity):
                result = await service.join_activity("join-snapshot", sync_calendar=False)

            self.assertTrue(result.success)
            enrolled = await ActivityRepository().list_enrolled(db_path)
            self.assertEqual([item.id for item in enrolled], ["join-snapshot"])
            self.assertTrue(enrolled[0].applied)

    async def test_cancel_success_deletes_latest_enrolled_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            db = SecondClassDB(db_path)
            await db.upsert_enrolled_secondclass(_sample_secondclass("cancel-snapshot"))

            activity = _sample_secondclass("cancel-snapshot")
            activity.cancel_apply = AsyncMock(return_value=True)

            service = EnrollmentService(
                auth_manager=FakeAuthManager(),
                calendar_sync_enabled=False,
                db_manager=FakeDBManager(db_path),
            )

            with patch("src.core.services.enrollment_service.SecondClass", return_value=activity):
                result = await service.cancel_activity("cancel-snapshot", "报名快照活动")

            self.assertTrue(result.success)
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM enrolled_secondclass WHERE id = ?",
                    ("cancel-snapshot",),
                ).fetchone()
            self.assertEqual(row[0], 0)


if __name__ == "__main__":
    unittest.main()
