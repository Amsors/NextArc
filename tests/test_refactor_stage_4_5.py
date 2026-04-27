"""阶段 4/5 重构回归测试。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pyustc.young import SecondClass, Status

from src.context import ContextManager, ContextRecord, ContextType, SearchResultPayload
from src.core.filtering import ActivityFilterPipeline, FilterContext
from src.core.secondclass_db import SecondClassDB
from src.core.user_preference_manager import UserPreferenceManager
from src.models.filter_result import FilteredActivity


def _activity(
    activity_id: str,
    name: str,
    status: int = Status.APPLYING.code,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SecondClass:
    data = {
        "id": activity_id,
        "itemName": name,
        "itemStatus": status,
        "booleanRegistration": "0",
        "needSignInfo": "0",
        "itemCategory": "0",
    }
    if start:
        data["st"] = start.strftime("%Y-%m-%d %H:%M:%S")
    if end:
        data["et"] = end.strftime("%Y-%m-%d %H:%M:%S")
    return SecondClass.from_dict(data)


def _activity_row(
    activity_id: str,
    name: str,
    hold_time: dict | None = None,
    participation_form: str | None = None,
) -> dict:
    return {
        "id": activity_id,
        "name": name,
        "status": Status.APPLYING.code,
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
        "place_info": None,
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


class RejectAllTimeFilter:
    def filter_activities(
        self,
        activities: list[SecondClass],
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        return [], [
            FilteredActivity(
                activity=activity,
                reason="测试时间冲突",
                filter_type="time",
            )
            for activity in activities
        ]


class ActivityFilterPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_interested_restore_bypasses_user_filters_but_not_enrolled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, "enrolled_secondclass", _activity_row("enrolled", "已报名白名单"))

            manager = UserPreferenceManager(Path(tmp_dir) / "preference.db")
            await manager.initialize()
            await manager.add_interested_activities(["white", "enrolled"])

            pipeline = ActivityFilterPipeline(
                user_preference_manager=manager,
                time_filter=RejectAllTimeFilter(),
                use_time_filter=True,
            )

            result = await pipeline.apply(
                [
                    _activity("white", "白名单活动"),
                    _activity("normal", "普通活动"),
                    _activity("enrolled", "已报名白名单"),
                ],
                FilterContext(
                    latest_db=db_path,
                    allowed_statuses=[Status.APPLYING, Status.PUBLISHED],
                    ignore_overlap=False,
                    source="test",
                ),
            )

            self.assertEqual([activity.id for activity in result.kept], ["white"])
            self.assertEqual([item.activity.id for item in result.filtered["enrolled"]], ["enrolled"])
            self.assertEqual([item.activity.id for item in result.filtered["time"]], ["normal"])
            self.assertIn("感兴趣白名单已恢复 1 个活动", result.summaries)

    async def test_ignore_overlap_controls_overlay_filter_behavior(self) -> None:
        now = datetime.now() + timedelta(days=1)
        now = now.replace(hour=9, minute=0, second=0, microsecond=0)
        enrolled_time = {
            "start": now.strftime("%Y-%m-%d %H:%M:%S"),
            "end": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "snapshot.db"
            SecondClassDB(db_path)
            _insert_row(db_path, "enrolled_secondclass", _activity_row("enrolled", "已报名活动", enrolled_time))

            activity = _activity(
                "candidate",
                "候选活动",
                start=now + timedelta(minutes=30),
                end=now + timedelta(hours=1),
            )
            pipeline = ActivityFilterPipeline()

            kept_result = await pipeline.apply(
                [activity],
                FilterContext(
                    latest_db=db_path,
                    ignore_overlap=False,
                    apply_enrolled_filter=False,
                    source="test",
                ),
            )
            self.assertEqual([item.id for item in kept_result.kept], ["candidate"])
            self.assertIn("candidate", kept_result.overlap_reasons)
            self.assertEqual(kept_result.filtered["overlay"], [])

            filtered_result = await pipeline.apply(
                [activity],
                FilterContext(
                    latest_db=db_path,
                    ignore_overlap=True,
                    apply_enrolled_filter=False,
                    source="test",
                ),
            )
            self.assertEqual(filtered_result.kept, [])
            self.assertEqual([item.activity.id for item in filtered_result.filtered["overlay"]], ["candidate"])


class ContextManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_context_expiration_policies(self) -> None:
        manager = ContextManager()
        activity = _activity("a1", "测试活动")

        await manager.set_search_result("测试", [activity])
        search_record = await manager.get(ContextType.SEARCH_RESULT)
        self.assertIsNotNone(search_record)
        self.assertEqual(search_record.expires_at - search_record.created_at, timedelta(minutes=5))

        await manager.set_confirmation("join", activity.id, activity.name)
        confirmation_record = await manager.get(ContextType.CONFIRMATION)
        self.assertIsNotNone(confirmation_record)
        self.assertEqual(confirmation_record.expires_at - confirmation_record.created_at, timedelta(minutes=2))

        await manager.set_displayed_activities([activity], ttl=timedelta(seconds=-1))
        self.assertIsNone(await manager.get_displayed_activities())

    async def test_expired_context_is_cleaned_on_read(self) -> None:
        manager = ContextManager()
        now = datetime.now()
        await manager.set(
            ContextRecord(
                type=ContextType.SEARCH_RESULT,
                payload=SearchResultPayload(keyword="旧", results=[]),
                created_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(seconds=1),
                source="test",
            )
        )

        self.assertIsNone(await manager.get_search_result())
        self.assertIsNone(await manager.get(ContextType.SEARCH_RESULT))


if __name__ == "__main__":
    unittest.main()
