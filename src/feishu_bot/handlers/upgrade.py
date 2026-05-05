"""/upgrade 指令处理器"""

import asyncio
import re

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
        if not self.check_dependencies():
            return Response.text("服务未初始化")
        if not self._maintenance_service:
            return Response.text("运行时维护服务未初始化，无法升级")

        logger.info("执行 /upgrade 指令 - 检查更新")
        version_checker = self._scanner.version_checker
        if not version_checker:
            return Response.text("版本检查器未启用，请在配置中开启版本检查功能")

        if not version_checker.is_git_repo():
            return Response.text("当前目录不是 git 仓库，无法自动更新")

        try:
            logger.info("正在 fetch 远程仓库...")
            fetch_result = await version_checker.fetch_remote_result()
            if not fetch_result.success:
                if version_checker.is_permission_error(fetch_result.stderr):
                    return await self._handle_readonly_upgrade_check(session, fetch_result.stderr)

                return Response.text(
                    "无法连接到远程仓库\n"
                    "\n"
                    f"错误信息: {fetch_result.stderr or 'unknown'}\n"
                    "\n"
                    "请检查网络连接、远程仓库地址和访问权限是否正常\n"
                )

            logger.info("正在检查版本差异...")
            result = await version_checker.check_for_updates(auto_fetch=False)
            current_branch = await version_checker.get_current_branch()
            target_branch = version_checker.config.branch_name

            if result is None:
                if current_branch != target_branch:
                    current_sha = await version_checker.get_current_version()
                    latest_sha = await version_checker.get_remote_version()
                    if not current_sha or not latest_sha:
                        return Response.text("无法获取当前版本或目标分支版本，请检查 git 仓库状态")

                    await session.context_manager.set_confirmation(
                        operation="upgrade",
                        data={
                            "current_sha": current_sha,
                            "latest_sha": latest_sha,
                            "current_branch": current_branch or "detached",
                            "target_branch": target_branch,
                            "commits": [],
                        }
                    )

                    return Response.text(
                        "当前代码已无新增提交需要拉取，但运行分支与配置不一致。\n"
                        "\n"
                        f"当前分支: {current_branch or 'detached'}\n"
                        f"目标分支: {target_branch}\n"
                        f"目标版本: {latest_sha[:7]}\n"
                        "\n"
                        "更新后将切换到目标分支并自动重启应用。\n"
                        "\n"
                        "是否立即切换并重启？(回复「确认」或「取消」)"
                    )

                current_sha = await version_checker.get_current_version()
                current_short = current_sha[:7] if current_sha else "unknown"
                return Response.text(
                    f"当前已是最新版本，无需更新。\n"
                    f"\n"
                    f"当前分支: {current_branch or 'detached'}\n"
                    f"当前版本: {current_short}"
                )

            logger.info(f"发现新版本: {result.current_sha[:7]} -> {result.latest_sha[:7]}")

            await session.context_manager.set_confirmation(
                operation="upgrade",
                data={
                    "current_sha": result.current_sha,
                    "latest_sha": result.latest_sha,
                    "current_branch": current_branch or "detached",
                    "target_branch": target_branch,
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
                f"当前分支: {current_branch or 'detached'}",
                f"目标分支: {target_branch}",
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

    async def _handle_readonly_upgrade_check(self, session, fetch_error: str) -> Response:
        """主服务无权写 .git 时，改用只读远端查询完成升级确认。"""

        version_checker = self._scanner.version_checker
        current_sha = await version_checker.get_current_version()
        latest_sha = await version_checker.get_remote_head_version()
        current_branch = await version_checker.get_current_branch()
        target_branch = version_checker.config.branch_name

        if not current_sha or not latest_sha:
            return Response.text(
                "检查更新失败：当前服务无权写入本地 Git 目录，且无法读取远端目标分支。\n"
                "\n"
                f"fetch 错误: {fetch_error or 'unknown'}\n"
                "\n"
                "请确认 nextarc-upgrade.service 已安装，且远端仓库可以访问。"
            )

        branch_mismatch = current_branch != target_branch
        version_changed = current_sha != latest_sha
        if not branch_mismatch and not version_changed:
            return Response.text(
                "当前已是最新版本，无需更新。\n"
                "\n"
                f"当前分支: {current_branch or 'detached'}\n"
                f"当前版本: {current_sha[:7]}\n"
                "\n"
                "提示：当前服务进程无权写入本地 Git 目录，已使用只读远端检查。"
            )

        await session.context_manager.set_confirmation(
            operation="upgrade",
            data={
                "current_sha": current_sha,
                "latest_sha": latest_sha,
                "current_branch": current_branch or "detached",
                "target_branch": target_branch,
                "commits": [],
            }
        )

        lines = [
            "发现可升级的目标版本。",
            "",
            f"当前分支: {current_branch or 'detached'}",
            f"目标分支: {target_branch}",
            f"当前版本: {current_sha[:7]}",
            f"目标版本: {latest_sha[:7]}",
            "",
            "当前服务进程无权写入本地 Git 目录，已改用只读远端检查；更新内容列表暂不可用。",
            "确认后将由 nextarc-upgrade.service 拉取代码、安装依赖并重启应用。",
            "",
            "是否立即更新并重启？(回复「确认」或「取消」)",
        ]
        return Response.text("\n".join(lines))

    async def execute_upgrade(self, session) -> Response:
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation or confirmation.operation != "upgrade":
            return Response.text("升级会话已过期，请重新执行 /upgrade")

        version_checker = self._scanner.version_checker
        if not version_checker:
            await session.context_manager.clear_confirmation()
            return Response.text("版本检查器未启用，请重新执行 /upgrade")
        if not self._maintenance_service:
            await session.context_manager.clear_confirmation()
            return Response.text("运行时维护服务未初始化，无法升级")

        data = confirmation.data
        current_sha = data.get("current_sha", "")[:7]
        latest_sha = data.get("latest_sha", "")[:7]
        current_branch = data.get("current_branch", "unknown")
        target_branch = data.get("target_branch") or version_checker.config.branch_name

        logger.info(f"用户确认升级: {current_branch} -> {target_branch}, {current_sha} -> {latest_sha}")

        try:
            old_version = self._read_version_file()
            old_ver_str = self._version_to_str(old_version)
            logger.info(f"更新前版本号: {old_ver_str}")

            self._maintenance_service.write_upgrade_request(
                remote_name=version_checker.config.remote_name,
                branch_name=target_branch,
                old_version=old_ver_str if old_version is not None else None,
            )
            await session.context_manager.clear_confirmation()

            asyncio.create_task(self._delayed_trigger_upgrade_service())

            return Response.text(
                "已提交升级任务。\n"
                f"\n"
                f"分支: {current_branch} -> {target_branch}\n"
                f"当前: {current_sha}\n"
                f"目标: {latest_sha}\n"
                f"当前版本号: {old_ver_str}\n"
                f"\n"
                "后台升级服务将停止 NextArc、拉取 NextArc 和 pyustc、安装依赖并重新启动。"
            )

        except Exception as e:
            await session.context_manager.clear_confirmation()
            logger.error(f"升级过程异常: {e}")
            return Response.error(str(e), context="执行升级")

    async def _delayed_trigger_upgrade_service(self, delay: float = 3.0) -> None:
        await asyncio.sleep(delay)
        if not self._maintenance_service:
            logger.error("运行时维护服务未初始化，无法启动升级服务")
            return

        result = await self._maintenance_service.trigger_upgrade_service()
        if result.returncode != 0:
            logger.error(
                "启动升级服务失败: returncode=%s stdout=%s stderr=%s",
                result.returncode,
                result.stdout,
                result.stderr,
            )

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

    def _version_to_str(self, version: tuple[int, int, int] | None) -> str:
        if version is None:
            return "unknown"
        return f"{version[0]}.{version[1]}.{version[2]}"
