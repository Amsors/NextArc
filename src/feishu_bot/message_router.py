"""消息路由器"""
import traceback
from typing import TYPE_CHECKING

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .handlers import get_all_handlers, IgnoreHandler
from .handlers.cancel import CancelHandler
from .handlers.join import JoinHandler
from .handlers.upgrade import UpgradeHandler

if TYPE_CHECKING:
    from src.core import ActivityScanner, AuthManager, DatabaseManager
    from src.core.services import ActivityQueryService, ActivityUpdateService, EnrollmentService
    from src.core.user_preference_manager import UserPreferenceManager

logger = get_logger("feishu.router")


class MessageRouter:
    def __init__(self):
        self.handlers = get_all_handlers()

        self._confirm_handlers = {
            "cancel": CancelHandler(),
            "join": JoinHandler(),
            "upgrade": UpgradeHandler(),
        }

    def set_dependencies(
            self,
            scanner: "ActivityScanner",
            auth_manager: "AuthManager",
            db_manager: "DatabaseManager",
            ignore_manager: "UserPreferenceManager | None" = None,
            activity_query_service: "ActivityQueryService | None" = None,
            activity_update_service: "ActivityUpdateService | None" = None,
            enrollment_service: "EnrollmentService | None" = None,
    ):
        from .handlers.base import CommandHandler

        CommandHandler.set_dependencies(
            scanner,
            auth_manager,
            db_manager,
            activity_query_service,
            activity_update_service,
            enrollment_service,
        )

        for handler in self._confirm_handlers.values():
            handler._scanner = scanner
            handler._auth_manager = auth_manager
            handler._db_manager = db_manager
            handler._activity_query_service = activity_query_service
            handler._activity_update_service = activity_update_service
            handler._enrollment_service = enrollment_service

        if ignore_manager:
            IgnoreHandler.set_ignore_manager(ignore_manager)

    async def handle_message(self, text: str, session: UserSession) -> Response:
        text = text.strip()

        confirmation = await session.context_manager.get_confirmation()
        if confirmation:
            return await self._handle_confirmation(text, session)

        if text.startswith("/"):
            parts = text[1:].split()
        else:
            parts = text.split()

        if not parts:
            return Response.text("指令不能为空")

        cmd = parts[0].lower()
        args = parts[1:]

        handler = self.handlers.get(cmd)
        if not handler:
            return Response.text(f"未知指令: /{cmd}\n\n发送 /help 查看可用指令")

        try:
            return await handler.handle(args, session)
        except Exception as e:
            logger.error(f"处理指令 /{cmd} 失败: {e}")
            traceback.print_exc()
            return Response.error(str(e), context=f"处理指令 /{cmd}")

    async def _handle_confirmation(self, text: str, session: UserSession) -> Response:
        text = text.strip()
        confirmation = await session.context_manager.get_confirmation()
        if not confirmation:
            return Response.text("待确认操作已过期，请重新发起操作")

        if text == "确认":
            operation = confirmation.operation
            handler = self._confirm_handlers.get(operation)

            if handler is None:
                await session.context_manager.clear_confirmation()
                return Response.text(f"未知的操作类型: {operation}")

            execute_method = getattr(handler, f"execute_{operation}", None)
            if execute_method is None:
                await session.context_manager.clear_confirmation()
                return Response.text(f"操作 {operation} 未实现执行方法")

            return await execute_method(session)

        elif text == "取消":
            await session.context_manager.clear_confirmation()
            return Response.text("已取消操作")
        else:
            return Response.text(
                f"{confirmation.get_confirm_prompt()}\n\n"
                f"请回复「确认」或「取消」"
            )

    def get_help_message(self) -> Response:
        lines = ["NextArc - 第二课堂活动监控机器人\n", "可用指令："]

        for handler in self.handlers.values():
            lines.append(f"  /{handler.command} - {handler.get_usage()}")

        lines.append("")
        lines.append("搜索结果是有效期5分钟")

        return Response.text("\n".join(lines))
