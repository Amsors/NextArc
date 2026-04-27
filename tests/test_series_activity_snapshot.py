"""系列活动子活动快照写入回归测试。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.core.secondclass_db import SecondClassDB


class FakeStatus:
    code = "1"


class FakeSecondClass:
    def __init__(
        self,
        activity_id: str,
        name: str,
        *,
        is_series: bool = False,
        children: list["FakeSecondClass"] | None = None,
    ) -> None:
        self.id = activity_id
        self.name = name
        self.status = FakeStatus()
        self.create_time = None
        self.apply_time = None
        self.hold_time = None
        self.tel = ""
        self.valid_hour = None
        self.apply_num = None
        self.apply_limit = None
        self.applied = False
        self.need_sign_info = False
        self.module = None
        self.department = None
        self.labels = None
        self.conceive = ""
        self.is_series = is_series
        self.place_info = None
        self.participation_form = None
        self.data: dict = {}
        self.children = children or []
        self.updated = False

    async def get_children(self) -> list["FakeSecondClass"]:
        return self.children

    async def update(self) -> None:
        self.updated = True


def _snapshot_rows(db_path: Path) -> dict[str, sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, parent_id, children_id, deep_scaned FROM all_secondclass"
        ).fetchall()
    return {row["id"]: row for row in rows}


class SeriesActivitySnapshotTest(unittest.IsolatedAsyncioTestCase):
    async def test_series_children_are_not_written_when_expansion_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            child = FakeSecondClass("child", "子活动")
            parent = FakeSecondClass("parent", "系列活动", is_series=True, children=[child])

            await SecondClassDB(db_path).update_all_secondclass(
                [parent],
                deep_update=False,
                expand_series=False,
            )

            rows = _snapshot_rows(db_path)
            self.assertEqual(set(rows), {"parent"})
            self.assertIsNone(rows["parent"]["children_id"])
            self.assertFalse(child.updated)

    async def test_series_children_are_written_and_deep_update_follows_scan_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            child = FakeSecondClass("child", "子活动")
            parent = FakeSecondClass("parent", "系列活动", is_series=True, children=[child])

            await SecondClassDB(db_path).update_all_secondclass(
                [parent],
                deep_update=False,
                expand_series=True,
            )

            rows = _snapshot_rows(db_path)
            self.assertEqual(set(rows), {"parent", "child"})
            self.assertEqual(rows["child"]["parent_id"], "parent")
            self.assertEqual(rows["child"]["deep_scaned"], 0)
            self.assertFalse(parent.updated)
            self.assertFalse(child.updated)

            await SecondClassDB(db_path).update_all_secondclass(
                [parent],
                deep_update=True,
                expand_series=True,
            )

            rows = _snapshot_rows(db_path)
            self.assertEqual(rows["child"]["deep_scaned"], 1)
            self.assertTrue(parent.updated)
            self.assertTrue(child.updated)


if __name__ == "__main__":
    unittest.main()
