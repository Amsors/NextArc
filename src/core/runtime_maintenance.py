"""运行时维护操作入口。"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.utils.logger import get_logger

logger = get_logger("runtime_maintenance")

SAFE_GIT_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
SAFE_REMOTE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class MaintenanceCommandResult:
    """外部维护命令执行结果。"""

    returncode: int
    stdout: str
    stderr: str


class RuntimeMaintenanceService:
    """封装机器人可触发的重启和升级维护动作。"""

    def __init__(
        self,
        *,
        state_dir: Path,
        shutdown_callback: Callable[[], None],
        upgrade_service_name: str = "nextarc-upgrade.service",
    ) -> None:
        self.state_dir = Path(state_dir)
        self.shutdown_callback = shutdown_callback
        self.upgrade_service_name = upgrade_service_name

    @property
    def update_marker_path(self) -> Path:
        return self.state_dir / ".next_arc_updated"

    @property
    def upgrade_request_path(self) -> Path:
        return self.state_dir / "upgrade-request.env"

    @property
    def upgrade_status_path(self) -> Path:
        return self.state_dir / "upgrade-status.env"

    async def request_restart(self, delay: float = 5.0) -> None:
        """延迟请求应用退出，由 systemd 的 Restart 策略重新拉起。"""

        await asyncio.sleep(delay)
        logger.info("请求应用退出以触发服务重启")
        self.shutdown_callback()

    def write_upgrade_request(
        self,
        *,
        remote_name: str,
        branch_name: str,
        old_version: str | None,
    ) -> None:
        """写入供 root 级升级服务读取的升级请求。"""

        self._validate_remote(remote_name)
        self._validate_git_ref(branch_name)
        if old_version and not VERSION_PATTERN.fullmatch(old_version):
            raise ValueError(f"旧版本号格式无效: {old_version}")

        self.state_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"NEXTARC_UPGRADE_REMOTE={remote_name}",
            f"NEXTARC_UPGRADE_BRANCH={branch_name}",
            f"NEXTARC_OLD_VERSION={old_version or ''}",
        ]
        tmp_path = self.upgrade_request_path.with_name(f".{self.upgrade_request_path.name}.tmp")
        tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp_path.chmod(0o600)
        tmp_path.replace(self.upgrade_request_path)
        self.upgrade_request_path.chmod(0o600)
        logger.info("已写入升级请求: %s", self.upgrade_request_path)

    async def trigger_upgrade_service(self) -> MaintenanceCommandResult:
        """启动 systemd 升级服务。"""

        if os.geteuid() != 0 and self._no_new_privileges_enabled():
            message = (
                "当前进程启用了 NoNewPrivileges，跳过 sudo；"
                "升级请求将由 nextarc-upgrade.path 监听并触发"
            )
            logger.info(message)
            return MaintenanceCommandResult(0, message, "")

        command = self._build_systemctl_start_command()
        logger.info("启动升级服务: %s", " ".join(command))
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return MaintenanceCommandResult(
                returncode=proc.returncode,
                stdout=stdout.decode("utf-8", errors="replace").strip(),
                stderr=stderr.decode("utf-8", errors="replace").strip(),
            )
        except FileNotFoundError as exc:
            logger.error("无法启动 systemd 升级服务: %s", exc)
            return MaintenanceCommandResult(1, "", str(exc))

    def _build_systemctl_start_command(self) -> list[str]:
        systemctl = shutil.which("systemctl") or "/bin/systemctl"
        if os.geteuid() == 0:
            return [systemctl, "start", "--no-block", self.upgrade_service_name]
        return ["sudo", "-n", systemctl, "start", "--no-block", self.upgrade_service_name]

    def _no_new_privileges_enabled(self) -> bool:
        """读取 Linux 进程状态，判断 sudo 是否会被 NoNewPrivileges 拦截。"""

        status_path = Path("/proc/self/status")
        try:
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("NoNewPrivs:"):
                    return line.split(":", 1)[1].strip() == "1"
        except OSError as exc:
            logger.debug("读取 NoNewPrivileges 状态失败: %s", exc)
        return False

    def _validate_remote(self, remote_name: str) -> None:
        if not remote_name or not SAFE_REMOTE_PATTERN.fullmatch(remote_name):
            raise ValueError(f"远程仓库名称不安全: {remote_name}")

    def _validate_git_ref(self, branch_name: str) -> None:
        if (
            not branch_name
            or branch_name.startswith("-")
            or ".." in branch_name
            or branch_name.endswith(".lock")
            or not SAFE_GIT_REF_PATTERN.fullmatch(branch_name)
        ):
            raise ValueError(f"分支名称不安全: {branch_name}")
