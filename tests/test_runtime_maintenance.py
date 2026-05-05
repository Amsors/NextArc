"""运行时维护服务回归测试。"""

import tempfile
import unittest
from pathlib import Path

from src.core.runtime_maintenance import RuntimeMaintenanceService
from src.feishu_bot.message_router import MessageRouter


class RuntimeMaintenanceServiceTest(unittest.TestCase):
    def test_write_upgrade_request_uses_state_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = RuntimeMaintenanceService(
                state_dir=Path(tmpdir),
                shutdown_callback=lambda: None,
            )

            service.write_upgrade_request(
                remote_name="origin",
                branch_name="feat/one_click_deploy",
                old_version="2.6.0",
            )

            request = service.upgrade_request_path.read_text(encoding="utf-8")
            self.assertIn("NEXTARC_UPGRADE_REMOTE=origin", request)
            self.assertIn("NEXTARC_UPGRADE_BRANCH=feat/one_click_deploy", request)
            self.assertIn("NEXTARC_OLD_VERSION=2.6.0", request)

    def test_write_upgrade_request_rejects_unsafe_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = RuntimeMaintenanceService(
                state_dir=Path(tmpdir),
                shutdown_callback=lambda: None,
            )

            with self.assertRaises(ValueError):
                service.write_upgrade_request(
                    remote_name="origin",
                    branch_name="../main",
                    old_version="2.6.0",
                )


class MessageRouterMaintenanceConfirmationTest(unittest.TestCase):
    def test_router_registers_restart_and_upgrade_confirm_handlers(self) -> None:
        router = MessageRouter(app_context=object())

        self.assertIn("restart", router._confirm_handlers)
        self.assertIn("upgrade", router._confirm_handlers)


if __name__ == "__main__":
    unittest.main()
