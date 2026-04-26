"""阶段 6/7 重构回归测试。"""

import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pyustc.young import SecondClass, Status

from src.core.events import EventBus
from src.core.events.scan_events import EnrolledActivityChangedEvent, NewActivitiesFoundEvent
from src.core.scanning.sync_service import ActivitySyncService
from src.core.scanning import ScanCoordinator, ScanOptions, SyncResult
from src.core.services import ActivityUpdateResult
from src.feishu_bot.handlers import get_all_handlers
from src.feishu_bot.handlers.base import CommandHandler
from src.models.diff_result import ActivityChange, DiffResult, FieldChange
from src.notifications.listener import NotificationDeliveryError, NotificationListener
from src.notifications.service import NotificationService
from src.core.filtering import FilterPipelineResult


def _activity(activity_id: str, name: str = "测试活动") -> SecondClass:
    return SecondClass.from_dict(
        {
            "id": activity_id,
            "itemName": name,
            "itemStatus": Status.APPLYING.code,
            "booleanRegistration": "0",
            "needSignInfo": "0",
            "itemCategory": "0",
        }
    )


class FakeDBManager:
    def __init__(self) -> None:
        self.old_db = Path("old.db")
        self.new_db = Path("new.db")

    def get_previous_db(self) -> Path:
        return self.old_db

    def get_new_db_path(self) -> Path:
        return self.new_db

    def get_latest_db(self) -> Path:
        return self.new_db

    def cleanup_old_dbs(self) -> int:
        return 0


class FakeSyncService:
    async def sync(self, target_db: Path, deep_update: bool) -> SyncResult:
        return SyncResult(target_db=target_db, activity_count=1, enrolled_count=0)


class FakeDiffService:
    async def diff(self, old_db_path: Path, new_db_path: Path) -> DiffResult:
        return DiffResult(
            added=[
                ActivityChange(
                    activity_id="a1",
                    activity_name="新活动",
                    change_type="added",
                )
            ]
        )

    async def get_enrolled_changes(self, diff: DiffResult, new_db_path: Path) -> list:
        return []


class TrackingEnrolledDiffService(FakeDiffService):
    def __init__(self) -> None:
        self.get_enrolled_changes_called = False

    async def get_enrolled_changes(self, diff: DiffResult, new_db_path: Path) -> list:
        self.get_enrolled_changes_called = True
        return []


class FakeActivityUpdateService:
    async def update_activities(
        self,
        activities: list[SecondClass],
        max_concurrent: int | None = None,
        continue_on_error: bool = True,
    ) -> ActivityUpdateResult:
        return ActivityUpdateResult(successful=[_activity("a1", "新活动")], failed=[])


class PassThroughPipeline:
    async def apply(self, activities: list[SecondClass], context) -> FilterPipelineResult:
        return FilterPipelineResult(kept=activities, filtered={}, summaries=[])


class FakeActivityRepositoryCounts:
    async def count_all(self, db_path: Path) -> int:
        return 0

    async def count_enrolled(self, db_path: Path) -> int:
        return 0


class FakeAuthManager:
    @asynccontextmanager
    async def create_session_once(self):
        yield


async def _empty_secondclass_generator():
    if False:
        yield _activity("unused")


class ActivitySyncServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_enrolled_sync_always_deep_updates_before_writing(self) -> None:
        class RecordingSecondClassDB:
            def __init__(self, db_path: Path) -> None:
                self.db_path = db_path
                self.all_deep_update: bool | None = None
                self.expand_series: bool | None = None
                self.enrolled_deep_update: bool | None = None

            async def update_all_from_generator(
                self,
                sc_generator,
                expand_series: bool,
                deep_update: bool,
            ) -> None:
                self.all_deep_update = deep_update
                self.expand_series = expand_series
                async for _ in sc_generator:
                    pass

            async def update_enrolled_from_generator(
                self,
                sc_generator,
                deep_update: bool,
            ) -> None:
                self.enrolled_deep_update = deep_update
                async for _ in sc_generator:
                    pass

        db_instances: list[RecordingSecondClassDB] = []

        def build_db(db_path: Path) -> RecordingSecondClassDB:
            db = RecordingSecondClassDB(db_path)
            db_instances.append(db)
            return db

        service = ActivitySyncService(
            auth_manager=FakeAuthManager(),
            activity_repository=FakeActivityRepositoryCounts(),
        )

        with (
            patch("src.core.scanning.sync_service.SecondClassDB", side_effect=build_db),
            patch.object(SecondClass, "find", return_value=_empty_secondclass_generator()),
            patch.object(SecondClass, "get_participated", return_value=_empty_secondclass_generator()),
        ):
            await service.sync(Path("snapshot.db"), deep_update=False)

        self.assertEqual(len(db_instances), 1)
        self.assertFalse(db_instances[0].all_deep_update)
        self.assertFalse(db_instances[0].expand_series)
        self.assertTrue(db_instances[0].enrolled_deep_update)

    async def test_sync_passes_series_expansion_config_to_all_activity_snapshot(self) -> None:
        class RecordingSecondClassDB:
            def __init__(self, db_path: Path) -> None:
                self.db_path = db_path
                self.expand_series: bool | None = None
                self.all_deep_update: bool | None = None

            async def update_all_from_generator(
                self,
                sc_generator,
                expand_series: bool,
                deep_update: bool,
            ) -> None:
                self.expand_series = expand_series
                self.all_deep_update = deep_update
                async for _ in sc_generator:
                    pass

            async def update_enrolled_from_generator(
                self,
                sc_generator,
                deep_update: bool,
            ) -> None:
                async for _ in sc_generator:
                    pass

        db_instances: list[RecordingSecondClassDB] = []

        def build_db(db_path: Path) -> RecordingSecondClassDB:
            db = RecordingSecondClassDB(db_path)
            db_instances.append(db)
            return db

        service = ActivitySyncService(
            auth_manager=FakeAuthManager(),
            activity_repository=FakeActivityRepositoryCounts(),
            add_sub_secondclass_into_db=True,
        )

        with (
            patch("src.core.scanning.sync_service.SecondClassDB", side_effect=build_db),
            patch.object(SecondClass, "find", return_value=_empty_secondclass_generator()),
            patch.object(SecondClass, "get_participated", return_value=_empty_secondclass_generator()),
        ):
            await service.sync(Path("snapshot.db"), deep_update=True)

        self.assertEqual(len(db_instances), 1)
        self.assertTrue(db_instances[0].expand_series)
        self.assertTrue(db_instances[0].all_deep_update)


class FailingNotificationService(NotificationService):
    async def send_text(self, message: str) -> bool:
        return False

    async def send_card(self, card_content: dict) -> bool:
        return False


class RecordingNotificationService(NotificationService):
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, message: str) -> bool:
        self.messages.append(message)
        return True

    async def send_card(self, card_content: dict) -> bool:
        return True


class EventBusResultTest(unittest.IsolatedAsyncioTestCase):
    async def test_publish_returns_listener_failure(self) -> None:
        bus = EventBus()

        async def failing_listener(event) -> None:
            raise RuntimeError("listener failed")

        bus.subscribe(NewActivitiesFoundEvent, failing_listener)
        result = await bus.publish(
            NewActivitiesFoundEvent(
                activities=[],
                total_found=0,
                filters_applied={},
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(len(result.listener_results), 1)
        self.assertIn("listener failed", result.error_messages[0])

    async def test_scan_wait_notifications_records_publish_errors(self) -> None:
        bus = EventBus()

        async def failing_listener(event) -> None:
            raise RuntimeError("notification failed")

        bus.subscribe(NewActivitiesFoundEvent, failing_listener)
        coordinator = ScanCoordinator(
            db_manager=FakeDBManager(),
            sync_service=FakeSyncService(),
            diff_service=FakeDiffService(),
            event_bus=bus,
            filter_pipeline=PassThroughPipeline(),
            activity_update_service=FakeActivityUpdateService(),
        )

        result = await coordinator.scan(
            ScanOptions(
                deep_update=False,
                notify_diff=False,
                notify_enrolled_change=False,
                notify_new_activities=True,
                no_filter=False,
                wait_for_notifications=True,
            )
        )

        self.assertTrue(result.success)
        self.assertTrue(result.notification_errors)
        self.assertIn("notification failed", result.notification_errors[0])

    async def test_enrolled_change_detection_respects_global_config(self) -> None:
        diff_service = TrackingEnrolledDiffService()
        coordinator = ScanCoordinator(
            db_manager=FakeDBManager(),
            sync_service=FakeSyncService(),
            diff_service=diff_service,
            event_bus=EventBus(),
            filter_pipeline=PassThroughPipeline(),
            activity_update_service=FakeActivityUpdateService(),
            notify_enrolled_change_enabled=False,
        )

        result = await coordinator.scan(
            ScanOptions(
                deep_update=False,
                notify_diff=False,
                notify_enrolled_change=True,
                notify_new_activities=False,
                no_filter=False,
                wait_for_notifications=True,
            )
        )

        self.assertTrue(result.success)
        self.assertFalse(diff_service.get_enrolled_changes_called)
        self.assertEqual(result.enrolled_changes, [])


class NotificationListenerTest(unittest.IsolatedAsyncioTestCase):
    async def test_listener_raises_when_card_send_returns_false(self) -> None:
        listener = NotificationListener(FailingNotificationService())

        with self.assertRaises(NotificationDeliveryError):
            await listener.on_new_activities_found(
                NewActivitiesFoundEvent(
                    activities=[_activity("a1")],
                    total_found=1,
                    filters_applied={},
                )
            )

    async def test_enrolled_change_notification_is_single_message_without_duplicate_title(self) -> None:
        service = RecordingNotificationService()
        listener = NotificationListener(service)

        await listener.on_enrolled_activity_changed(
            EnrolledActivityChangedEvent(
                changes=[
                    ActivityChange(
                        activity_id="a1",
                        activity_name="活动一",
                        change_type="modified",
                        field_changes=[
                            FieldChange(field_name="hold_time", old_value="旧时间", new_value="新时间")
                        ],
                    ),
                    ActivityChange(
                        activity_id="a2",
                        activity_name="活动二",
                        change_type="modified",
                        field_changes=[
                            FieldChange(field_name="place_info", old_value="旧地点", new_value="新地点")
                        ],
                    ),
                ]
            )
        )

        self.assertEqual(len(service.messages), 1)
        message = service.messages[0]
        self.assertIn("已报名活动有更新（共 2 个）", message)
        self.assertIn("[1] 活动一", message)
        self.assertIn("[2] 活动二", message)
        self.assertEqual(message.count("活动一"), 1)
        self.assertEqual(message.count("活动二"), 1)


class HandlerInjectionTest(unittest.TestCase):
    def test_handlers_use_instance_app_context(self) -> None:
        app_context = SimpleNamespace(scanner=object())
        handlers = get_all_handlers(app_context)

        self.assertFalse(hasattr(CommandHandler, "set_dependencies"))
        self.assertIs(handlers["help"].app_context, app_context)
        self.assertIs(handlers["valid"].app_context, app_context)


if __name__ == "__main__":
    unittest.main()
