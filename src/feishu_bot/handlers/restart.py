"""/restart 指令处理器"""

import asyncio
import os
import sys

from src.notifications import Response
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.restart")


class RestartHandler(CommandHandler):
    """处理机器人自我重启指令。"""

    @property
    def command(self) -> str:
        return "restart"

    def get_usage(self) -> str:
        return "/restart - 重启应用"

    async def handle(self, args: list[str], session) -> Response:
        logger.info("执行 /restart 指令 - 当前已禁用")
        return Response.text("机器人内自重启功能已暂时禁用，请通过 systemd 管理服务。")

    async def execute_restart(self, session) -> Response:
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation or confirmation.operation != "restart":
            return Response.text("重启会话已过期，请重新执行 /restart")

        await session.context_manager.clear_confirmation()
        logger.info("用户确认重启应用")

        asyncio.create_task(self._delayed_restart())

        return Response.text("正在重启应用...")

    async def _delayed_restart(self, delay: float = 5.0) -> None:
        await asyncio.sleep(delay)
        self._restart_application()

    def _restart_application(self) -> None:
        executable = sys.executable
        args = sys.argv

        logger.info(f"重启命令: {executable} {' '.join(args)}")

        try:
            os.execv(executable, [executable] + args)
        except Exception as e:
            logger.error(f"重启失败: {e}")
