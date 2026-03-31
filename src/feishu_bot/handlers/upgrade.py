"""/upgrade 指令处理器"""

import asyncio
import os
import re
import sys
from pathlib import Path

from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.upgrade")

VERSION_FILE_NAME = ".next_arc_version"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class UpgradeHandler(CommandHandler):

    @property
    def command(self) -> str:
        return "upgrade"

    def get_usage(self) -> str:
        return "/upgrade - 检查并安装程序更新"

    async def handle(self, args: list[str], session) -> Response:
        """处理 /upgrade 指令"""
        if not self.check_dependencies():
            return Response.text("服务未初始化")

        logger.info("执行 /upgrade 指令 - 检查更新")

        version_checker = self._scanner.version_checker
        if not version_checker:
            return Response.text("版本检查器未启用，请在配置中开启版本检查功能")

        if not version_checker.is_git_repo():
            return Response.text("当前目录不是 git 仓库，无法自动更新")

        try:
            logger.info("正在 fetch 远程仓库...")
            fetch_success = await version_checker.fetch_remote()
            if not fetch_success:
                return Response.text(
                    "无法连接到远程仓库\n"
                    "\n"
                    "请检查网络连接是否正常\n"
                )

            logger.info("正在检查版本差异...")
            result = await version_checker.check_for_updates()

            if result is None:
                current_sha = await version_checker.get_current_version()
                current_short = current_sha[:7] if current_sha else "unknown"
                return Response.text(
                    f"当前已是最新版本，无需更新。\n"
                    f"\n"
                    f"当前版本: {current_short}"
                )

            logger.info(f"发现新版本: {result.current_sha[:7]} -> {result.latest_sha[:7]}")

            session.set_confirm(
                operation="upgrade",
                data={
                    "current_sha": result.current_sha,
                    "latest_sha": result.latest_sha,
                    "commits": [
                        {
                            "sha": c.sha,
                            "message": c.message,
                            "author": c.author,
                        }
                        for c in result.new_commits
                    ],
                }
            )

            lines = [
                "发现新版本！",
                "",
                f"当前版本: {result.current_sha[:7]}",
                f"最新版本: {result.latest_sha[:7]}",
                f"落后提交: {result.commits_behind} 个",
                "",
                "更新内容：",
            ]

            for i, commit in enumerate(result.new_commits[:10], 1):
                message = commit.message[:40] + "..." if len(commit.message) > 40 else commit.message
                lines.append(f"  {i}. {message}")

            if len(result.new_commits) > 10:
                lines.append(f"  ... 还有 {len(result.new_commits) - 10} 个提交")

            lines.extend([
                "",
                "更新后将自动重启应用",
                "",
                "是否立即更新并重启？(回复「确认」或「取消」)",
            ])

            return Response.text("\n".join(lines))

        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            return Response.error(str(e), context="检查更新")

    async def execute_upgrade(self, session) -> Response:
        if not session.confirm or session.confirm.operation != "upgrade":
            return Response.text("升级会话已过期，请重新执行 /upgrade")

        data = session.confirm.data
        current_sha = data.get("current_sha", "")[:7]
        latest_sha = data.get("latest_sha", "")[:7]

        logger.info(f"用户确认升级: {current_sha} -> {latest_sha}")

        version_checker = self._scanner.version_checker

        # 读取更新前的版本号
        old_version = self._read_version_file()
        logger.info(f"更新前版本号: {old_version}")

        # 发送正在更新的消息
        progress_msg = (
            "正在执行更新...\n"
            f"  当前: {current_sha}\n"
            f"  目标: {latest_sha}"
        )

        try:
            logger.info("执行 git pull...")
            returncode, stdout, stderr = await self._run_git_pull(version_checker)

            if returncode != 0:
                # git pull 失败
                session.clear_confirm()
                error_detail = self._parse_git_error(stderr, stdout)
                logger.error(f"git pull 失败: {error_detail}")

                return Response.text(
                    f"更新失败\n"
                    f"\n"
                    f"错误信息：{error_detail}\n"
                    f"\n"
                    f"请联系开发者。\n"
                    f"当前版本保持不变: {current_sha}"
                )

            logger.info("git pull 成功")

            new_version = self._read_version_file()
            logger.info(f"更新后版本号: {new_version}")

            version_changed, old_ver_str, new_ver_str = self._compare_versions(old_version, new_version)

            session.clear_confirm()

            version_info = ""
            if version_changed:
                version_info = f"\n版本号: {old_ver_str} → {new_ver_str}\n"
                logger.info(f"版本号发生变化: {old_ver_str} -> {new_ver_str}")

            success_msg = (
                f"更新成功！\n"
                f"\n"
                f"已更新至: {latest_sha}\n"
                f"\n"
                f"正在重启应用..."
            )

            major_version_changed = self._is_major_version_changed(old_version, new_version)
            if major_version_changed:
                logger.warning(f"主版本号发生变化: {old_ver_str} -> {new_ver_str}")

            # 发送版本变更通知（在返回响应后、重启前）
            await self._send_version_notifications(old_version, new_version, major_version_changed)

            # 延迟重启
            asyncio.create_task(self._delayed_restart())

            return Response.text(success_msg)

        except Exception as e:
            session.clear_confirm()
            logger.error(f"升级过程异常: {e}")
            return Response.error(str(e), context="执行升级")

    async def _run_git_pull(self, version_checker) -> tuple[int, str, str]:
        """执行 git pull 命令

        Returns:
            tuple: (returncode, stdout, stderr)
        """
        project_root = version_checker.project_root

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "pull",
                version_checker.config.remote_name,
                version_checker.config.branch_name,
                cwd=project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return (
                proc.returncode,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )
        except FileNotFoundError:
            return (1, "", "git command not found")
        except Exception as e:
            return (1, "", str(e))

    def _parse_git_error(self, stderr: str, stdout: str) -> str:
        error_lower = stderr.lower()

        if "conflict" in error_lower:
            return "存在代码冲突，请联系开发者"
        elif "could not resolve host" in error_lower or "unable to access" in error_lower:
            return "网络连接失败，无法连接到远程仓库"
        elif "authentication failed" in error_lower or "permission denied" in error_lower:
            return "权限不足，请检查 git 认证配置"
        elif "merge" in error_lower and "abort" in error_lower:
            return "合并被中止，可能存在冲突，请联系开发者"
        elif stderr:
            return stderr[:100] + ("..." if len(stderr) > 100 else "")
        elif stdout:
            return stdout[:100] + ("..." if len(stdout) > 100 else "")
        else:
            return "未知错误"

    async def _delayed_restart(self, delay: float = 5.0):
        await asyncio.sleep(delay)
        self._restart_application()

    async def _send_version_notifications(
            self,
            old_version: tuple[int, int, int] | None,
            new_version: tuple[int, int, int] | None,
            major_changed: bool
    ):
        if not self._message_sender or not (old_version or new_version):
            return

        old_ver_str = self._version_to_str(old_version)
        new_ver_str = self._version_to_str(new_version)

        if old_ver_str == new_ver_str:
            return

        version_msg = (
            f"当前版本: {old_ver_str}\n"
            f"新版本: {new_ver_str}"
        )
        try:
            await self._message_sender.send(version_msg)
            logger.info(f"已发送版本变更通知: {old_ver_str} -> {new_ver_str}")
        except Exception as e:
            logger.error(f"发送版本变更通知失败: {e}")

        # 如果主版本号发生变化，发送额外警告
        if major_changed:
            warning_msg = (
                "重要提醒：主版本号发生变更！！！\n"
                "\n"
                "可能引入 breaking change，请于 GitHub 上查看最新版本文档，"
                "手动进行配置迁移，否则软件将无法运行，或部分功能将不可用！！！"
            )
            try:
                await self._message_sender.send(warning_msg)
                logger.warning("已发送主版本号变更警告")
            except Exception as e:
                logger.error(f"发送主版本号变更警告失败: {e}")

    def _read_version_file(self) -> tuple[int, int, int] | None:
        try:
            version_checker = self._scanner.version_checker
            version_file = version_checker.project_root / VERSION_FILE_NAME

            if not version_file.exists():
                logger.warning(f"版本文件不存在: {version_file}")
                return None

            content = version_file.read_text().strip()
            match = VERSION_PATTERN.match(content)

            if not match:
                logger.warning(f"版本号格式无效: {content}")
                return None

            x, y, z = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return (x, y, z)

        except Exception as e:
            logger.error(f"读取版本文件失败: {e}")
            return None

    def _compare_versions(
            self,
            old: tuple[int, int, int] | None,
            new: tuple[int, int, int] | None
    ) -> tuple[bool, str, str]:
        old_str = self._version_to_str(old)
        new_str = self._version_to_str(new)
        changed = old_str != new_str
        return (changed, old_str, new_str)

    def _is_major_version_changed(
            self,
            old: tuple[int, int, int] | None,
            new: tuple[int, int, int] | None
    ) -> bool:
        if old is None or new is None:
            return False
        return old[0] != new[0]

    def _version_to_str(self, version: tuple[int, int, int] | None) -> str:
        if version is None:
            return "unknown"
        return f"{version[0]}.{version[1]}.{version[2]}"

    def _restart_application(self):
        """使用 os.execv 替换当前进程，保持相同的命令行参数"""
        logger.info("正在重启应用...")

        # 创建更新标记文件
        self._create_update_marker()

        executable = sys.executable
        args = sys.argv

        logger.info(f"重启命令: {executable} {' '.join(args)}")

        # 使用 os.execv 替换当前进程
        try:
            os.execv(executable, [executable] + args)
        except Exception as e:
            logger.error(f"重启失败: {e}")

    def _create_update_marker(self):
        try:
            project_root = self._scanner.version_checker.project_root
            marker_file = project_root / ".next_arc_updated"
            marker_file.touch()
            logger.info(f"已创建更新标记文件: {marker_file}")
        except Exception as e:
            logger.error(f"创建更新标记文件失败: {e}")
