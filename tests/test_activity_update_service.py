"""ActivityUpdateService 回归测试。"""

import unittest

from src.core.services.activity_update_service import ActivityUpdateService
import src.core.services.activity_update_service as activity_update_module


class FakeAuthContext:
    def __init__(self, auth_manager: "FakeAuthManager") -> None:
        self.auth_manager = auth_manager

    async def __aenter__(self):
        self.auth_manager.session_count += 1
        return object()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class FakeAuthManager:
    def __init__(self) -> None:
        self.session_count = 0

    def create_session_once(self) -> FakeAuthContext:
        return FakeAuthContext(self)


class FakeSecondClass:
    children: list["FakeSecondClass"] = []

    def __init__(self, activity_id: str, data: dict) -> None:
        self.id = activity_id
        self.data = data
        self.status = data.get("status", "open")
        self.is_series = data.get("is_series", False)
        self.updated = False

    async def update(self) -> None:
        self.updated = True
        if self.id == "parent":
            self.is_series = True

    async def get_children(self) -> list["FakeSecondClass"]:
        return self.children


class FakeBatchUpdater:
    last_instances: list[FakeSecondClass] = []

    def __init__(self, max_concurrent: int) -> None:
        self.max_concurrent = max_concurrent

    async def update_batch(
        self,
        instances: list[FakeSecondClass],
        continue_on_error: bool = True,
    ):
        self.__class__.last_instances = instances
        for instance in instances:
            instance.updated = True
        return instances, []


class ActivityUpdateServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_children_with_updates_uses_one_auth_session(self) -> None:
        auth_manager = FakeAuthManager()
        service = ActivityUpdateService(auth_manager)
        shown_child = FakeSecondClass("child-1", {"status": "open"})
        another_child = FakeSecondClass("child-2", {"status": "open"})
        hidden_child = FakeSecondClass("child-3", {"status": "closed"})
        FakeSecondClass.children = [shown_child, hidden_child, another_child]

        original_secondclass = activity_update_module.SecondClass
        original_batch_updater = activity_update_module.SecondClassBatchUpdater
        activity_update_module.SecondClass = FakeSecondClass
        activity_update_module.SecondClassBatchUpdater = FakeBatchUpdater
        try:
            result = await service.fetch_children_with_updates(
                "parent",
                child_filter=lambda child: child.status == "open",
                continue_on_error=True,
            )
        finally:
            activity_update_module.SecondClass = original_secondclass
            activity_update_module.SecondClassBatchUpdater = original_batch_updater
            FakeSecondClass.children = []

        self.assertEqual(auth_manager.session_count, 1)
        self.assertTrue(result.parent.updated)
        self.assertEqual([child.id for child in result.children], ["child-1", "child-2"])
        self.assertEqual([child.id for child in result.update_result.successful], ["child-1", "child-2"])
        self.assertEqual([child.id for child in FakeBatchUpdater.last_instances], ["child-1", "child-2"])
        self.assertTrue(shown_child.updated)
        self.assertTrue(another_child.updated)
        self.assertFalse(hidden_child.updated)
        FakeBatchUpdater.last_instances = []
