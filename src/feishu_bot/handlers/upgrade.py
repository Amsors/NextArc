"""/upgrade 指令处理器"""

import asyncio
import os
import sys

from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.upgrade")


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

            logger.info("git pull 成功，准备重启")

            session.clear_confirm()

            success_msg = (
                f"更新成功！\n"
                f"\n"
                f"已更新至: {latest_sha}\n"
                f"\n"
                f"正在重启应用..."
            )

            # 异步延迟重启，给消息发送留时间
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

    def _restart_application(self):
        """使用 os.execv 替换当前进程，保持相同的命令行参数"""
        logger.info("正在重启应用...")

        executable = sys.executable
        args = sys.argv

        logger.info(f"重启命令: {executable} {' '.join(args)}")

        # 使用 os.execv 替换当前进程
        try:
            os.execv(executable, [executable] + args)
        except Exception as e:
            logger.error(f"重启失败: {e}")
