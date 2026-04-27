"""阶段 8 pyustc 使用边界回归测试。"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pyustc.young import SecondClass, Status

from src.core.diff_engine import DiffEngine
from src.core.secondclass_db import SecondClassDB
from src.models.secondclass_mapper import secondclass_from_db_row, secondclass_to_db_row
from src.models.secondclass_view import (
    format_secondclass_for_list,
    get_department_name,
    get_module_name,
    get_participation_form,
    get_place_info,
)


def _clear_secondclass_cache(activity_id: str) -> None:
    SecondClass._instance_cache.pop(activity_id, None)


def _sample_secondclass(activity_id: str = "stage8-sample") -> SecondClass:
    _clear_secondclass_cache(activity_id)
    return SecondClass.from_dict(
        {
            "id": activity_id,
            "itemName": "阶段八活动",
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
            "needSignInfo": "1",
            "module": "m1",
            "moduleName": "文化素质",
            "businessDeptId": "d1",
            "bussinessDeptName": "校团委",
            "itemLable": "l1,l2",
            "lableNames": "讲座,实践",
            "conceive": "活动构想",
            "baseContent": "活动描述",
            "itemCategory": "1",
            "placeInfo": "西区活动室",
            "form": "0",
            "childrenIds": ["child-a", "child-b"],
            "parentId": "parent-a",
        }
    )


def _activity_row(
    activity_id: str,
    name: str,
    place_info: str | None = "西区活动室",
    participation_form: str | None = "0",
    scan_timestamp: int = 100,
    deep_scaned: int = 0,
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
        "department": None,
        "labels": None,
        "conceive": "",
        "is_series": 0,
        "place_info": place_info,
        "children_id": None,
        "parent_id": None,
        "scan_timestamp": scan_timestamp,
        "deep_scaned": deep_scaned,
        "deep_scaned_time": scan_timestamp if deep_scaned else None,
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


class SecondClassMapperViewTest(unittest.TestCase):
    def test_mapper_roundtrip_preserves_activity_fields_without_metadata_leak(self) -> None:
        activity = _sample_secondclass("stage8-mapper-roundtrip")
        activity.data["deep_scaned"] = "stale metadata"

        row = secondclass_to_db_row(
            activity,
            scan_timestamp=123,
            deep_scaned=True,
            deep_scaned_time=124,
        )

        self.assertEqual(row["place_info"], "西区活动室")
        self.assertEqual(row["participation_form"], "0")
        self.assertEqual(json.loads(row["children_id"]), ["child-a", "child-b"])
        self.assertEqual(row["parent_id"], "parent-a")
        self.assertTrue(row["deep_scaned"])

        restored = secondclass_from_db_row(row)

        self.assertEqual(restored.place_info, "西区活动室")
        self.assertEqual(get_participation_form(restored), "现场参与")
        self.assertEqual(restored.data["childrenIds"], ["child-a", "child-b"])
        self.assertEqual(restored.data["parentId"], "parent-a")
        self.assertEqual(get_module_name(restored), "文化素质")
        self.assertEqual(get_department_name(restored), "校团委")
        self.assertNotIn("deep_scaned", restored.data)
        self.assertNotIn("scan_timestamp", restored.data)

    def test_view_helpers_keep_existing_display_behavior(self) -> None:
        activity = _sample_secondclass("stage8-view")

        self.assertEqual(get_place_info(activity), "西区活动室")
        self.assertEqual(get_participation_form(activity), "现场参与")

        text = format_secondclass_for_list(activity, 1)
        self.assertIn("地点：西区活动室", text)
        self.assertIn("参与形式：现场参与", text)
        self.assertIn("模块：文化素质", text)


class DiffRowComparisonTest(unittest.IsolatedAsyncioTestCase):
    async def test_diff_compares_stable_rows_and_ignores_scan_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_db = Path(tmp_dir) / "old.db"
            new_db = Path(tmp_dir) / "new.db"
            SecondClassDB(old_db)
            SecondClassDB(new_db)

            _insert_row(old_db, "all_secondclass", _activity_row("same", "旧名称", "旧地点", "0"))
            _insert_row(old_db, "all_secondclass", _activity_row("removed", "删除活动"))

            _insert_row(
                new_db,
                "all_secondclass",
                _activity_row(
                    "same",
                    "新名称",
                    "新地点",
                    "1",
                    scan_timestamp=200,
                    deep_scaned=1,
                ),
            )
            _insert_row(new_db, "all_secondclass", _activity_row("added", "新增活动"))

            result = await DiffEngine().diff(old_db, new_db)

            self.assertEqual([change.activity_id for change in result.added], ["added"])
            self.assertEqual([change.activity_id for change in result.removed], ["removed"])
            self.assertEqual([change.activity_id for change in result.modified], ["same"])

            changed_fields = {
                change.field_name
                for change in result.modified[0].field_changes
            }
            self.assertIn("name", changed_fields)
            self.assertIn("place_info", changed_fields)
            self.assertIn("participation_form", changed_fields)
            self.assertNotIn("scan_timestamp", changed_fields)
            self.assertNotIn("deep_scaned", changed_fields)


if __name__ == "__main__":
    unittest.main()
