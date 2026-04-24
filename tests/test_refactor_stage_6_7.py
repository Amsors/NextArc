"""阶段 6/7 重构回归测试。"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from pyustc.young import SecondClass, Status

from src.core.events import EventBus
from src.core.events.scan_events import NewActivitiesFoundEvent
from src.core.scanning import ScanCoordinator, ScanOptions, SyncResult
from src.core.services import ActivityUpdateResult
from src.feishu_bot.handlers import get_all_handlers
from src.feishu_bot.handlers.base import CommandHandler
from src.models.diff_result import ActivityChange, DiffResult
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


class FailingNotificationService(NotificationService):
    async def send_text(self, message: str) -> bool:
        return False

    async def send_card(self, card_content: dict) -> bool:
        return False


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


class HandlerInjectionTest(unittest.TestCase):
    def test_handlers_use_instance_app_context(self) -> None:
        app_context = SimpleNamespace(scanner=object())
        handlers = get_all_handlers(app_context)

        self.assertFalse(hasattr(CommandHandler, "set_dependencies"))
        self.assertIs(handlers["help"].app_context, app_context)
        self.assertIs(handlers["valid"].app_context, app_context)


if __name__ == "__main__":
    unittest.main()
