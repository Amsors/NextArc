"""/restart 指令处理器"""

import asyncio

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
        if not self._maintenance_service:
            return Response.text("运行时维护服务未初始化，无法重启")

        await session.context_manager.set_confirmation(operation="restart")
        return Response.text(
            "即将重启 NextArc。\n"
            "\n"
            "确认后服务会先发送响应，再由 systemd 自动拉起新进程。\n"
            "\n"
            "是否立即重启？(回复「确认」或「取消」)"
        )

    async def execute_restart(self, session) -> Response:
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation or confirmation.operation != "restart":
            return Response.text("重启会话已过期，请重新执行 /restart")

        await session.context_manager.clear_confirmation()
        logger.info("用户确认重启应用")

        if not self._maintenance_service:
            return Response.text("运行时维护服务未初始化，无法重启")

        asyncio.create_task(self._maintenance_service.request_restart())

        return Response.text("正在重启应用...")
