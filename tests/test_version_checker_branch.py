"""版本更新分支切换行为回归测试。"""

import tempfile
import unittest
from pathlib import Path

from src.core.version_checker import VersionChecker


class _VersionConfig:
    enabled = True
    day_of_week = 6
    hour = 18
    minute = 0
    remote_name = "origin"
    branch_name = "feature/test"
    auto_fetch = True


class RecordingVersionChecker(VersionChecker):
    def __init__(self):
        super().__init__(_VersionConfig(), Path(tempfile.gettempdir()))
        self.commands: list[list[str]] = []
        self.current_branch: str | None = "master"
        self.branch_exists = False

    async def _run_git_command(self, args: list[str]) -> tuple[int, str, str]:
        self.commands.append(args)

        if args == ["branch", "--show-current"]:
            return (0, self.current_branch or "", "")

        if args[:3] == ["show-ref", "--verify", "--quiet"]:
            return (0 if self.branch_exists else 1, "", "")

        return (0, "", "")


class VersionCheckerBranchTest(unittest.IsolatedAsyncioTestCase):
    async def test_git_commands_trust_only_project_root(self) -> None:
        checker = RecordingVersionChecker()

        git_args = checker._build_git_command_args(["rev-parse", "HEAD"])

        self.assertEqual(
            git_args,
            [
                "-c",
                f"safe.directory={checker.project_root.resolve()}",
                "rev-parse",
                "HEAD",
            ],
        )

    async def test_fetch_remote_updates_configured_remote_tracking_branch(self) -> None:
        checker = RecordingVersionChecker()

        success = await checker.fetch_remote()

        self.assertTrue(success)
        self.assertEqual(
            checker.commands[-1],
            [
                "fetch",
                "origin",
                "+refs/heads/feature/test:refs/remotes/origin/feature/test",
            ],
        )

    async def test_fetch_remote_result_keeps_error_detail(self) -> None:
        checker = RecordingVersionChecker()

        async def fail_fetch(args: list[str]) -> tuple[int, str, str]:
            checker.commands.append(args)
            return (1, "", "error: cannot open '.git/FETCH_HEAD': Permission denied")

        checker._run_git_command = fail_fetch

        result = await checker.fetch_remote_result()

        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.stderr)

    async def test_permission_error_detects_git_write_failures(self) -> None:
        checker = RecordingVersionChecker()

        self.assertTrue(
            checker.is_permission_error("error: cannot open '.git/FETCH_HEAD': Permission denied")
        )
        self.assertTrue(checker.is_permission_error("fatal: could not lock config file .git/config"))
        self.assertFalse(checker.is_permission_error("fatal: unable to access remote"))

    async def test_get_remote_head_version_uses_readonly_ls_remote(self) -> None:
        checker = RecordingVersionChecker()

        async def run_git(args: list[str]) -> tuple[int, str, str]:
            checker.commands.append(args)
            if args[:2] == ["ls-remote", "--heads"]:
                return (
                    0,
                    "0123456789abcdef0123456789abcdef01234567\trefs/heads/feature/test",
                    "",
                )
            return (0, "", "")

        checker._run_git_command = run_git

        sha = await checker.get_remote_head_version()

        self.assertEqual(sha, "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(
            checker.commands[-1],
            ["ls-remote", "--heads", "origin", "refs/heads/feature/test"],
        )

    async def test_switch_to_existing_target_branch(self) -> None:
        checker = RecordingVersionChecker()
        checker.branch_exists = True

        returncode, _stdout, _stderr = await checker.switch_to_target_branch()

        self.assertEqual(returncode, 0)
        self.assertIn(["switch", "feature/test"], checker.commands)

    async def test_switch_creates_tracking_branch_when_missing_locally(self) -> None:
        checker = RecordingVersionChecker()

        returncode, _stdout, _stderr = await checker.switch_to_target_branch()

        self.assertEqual(returncode, 0)
        self.assertIn(
            ["switch", "--track", "-c", "feature/test", "origin/feature/test"],
            checker.commands,
        )


if __name__ == "__main__":
    unittest.main()
