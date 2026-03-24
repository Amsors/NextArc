"""消息路由器"""
import traceback
from typing import TYPE_CHECKING

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .handlers import get_all_handlers, IgnoreHandler
from .handlers.cancel import CancelHandler
from .handlers.join import JoinHandler

if TYPE_CHECKING:
    pass

logger = get_logger("feishu.router")


class MessageRouter:
    """消息路由器 - 处理用户消息并分发到相应处理器"""

    def __init__(self):
        self.handlers = get_all_handlers()
        self.cancel_handler = CancelHandler()
        self.join_handler = JoinHandler()

    def set_dependencies(self, scanner, auth_manager, db_manager, ignore_manager=None):
        """设置依赖的组件"""
        from .handlers.base import CommandHandler

        CommandHandler.set_dependencies(scanner, auth_manager, db_manager)

        # 同时为取消和报名处理器设置依赖（因为它们有额外的 execute 方法）
        self.cancel_handler._scanner = scanner
        self.cancel_handler._auth_manager = auth_manager
        self.cancel_handler._db_manager = db_manager

        self.join_handler._scanner = scanner
        self.join_handler._auth_manager = auth_manager
        self.join_handler._db_manager = db_manager

        # 设置忽略处理器依赖
        if ignore_manager:
            IgnoreHandler.set_ignore_manager(ignore_manager)

    async def handle_message(self, text: str, session: UserSession) -> Response:
        """
        处理用户消息

        Args:
            text: 用户输入的文本
            session: 用户会话

        Returns:
            Response 响应对象
        """
        text = text.strip()

        # 检查是否有待确认操作
        if session.confirm and not session.confirm.is_expired():
            return await self._handle_confirmation(text, session)

        # 去掉开头的 / 并分割
        if text.startswith("/"):
            parts = text[1:].split()
        else:
            parts = text.split()

        if not parts:
            return Response.text("❌ 指令不能为空")

        cmd = parts[0].lower()
        args = parts[1:]

        # 查找并执行处理器
        handler = self.handlers.get(cmd)
        if not handler:
            return Response.text(f"❌ 未知指令: /{cmd}\n\n发送 /alive 查看可用指令")

        try:
            return await handler.handle(args, session)
        except Exception as e:
            logger.error(f"处理指令 /{cmd} 失败: {e}")
            traceback.print_exc()
            return Response.error(str(e), context=f"处理指令 /{cmd}")

    async def _handle_confirmation(self, text: str, session: UserSession) -> Response:
        """
        处理确认操作

        Args:
            text: 用户响应（确认/取消）
            session: 用户会话

        Returns:
            Response 响应对象
        """
        text = text.strip()

        if text == "确认":
            operation = session.confirm.operation

            if operation == "cancel":
                return await self.cancel_handler.execute_cancel(session)
            elif operation == "join":
                return await self.join_handler.execute_join(session)
            else:
                session.clear_confirm()
                return Response.text("❌ 未知的操作类型")

        elif text == "取消":
            session.clear_confirm()
            return Response.text("✅ 已取消操作")
        else:
            # 不是确认或取消，提醒用户
            return Response.text(
                f"{session.confirm.get_confirm_prompt()}\n\n"
                f"⚠️ 请回复「确认」或「取消」"
            )

    def get_help_message(self) -> Response:
        """获取帮助信息"""
        lines = ["🤖 NextArc - 第二课堂活动监控机器人\n", "可用指令："]

        for handler in self.handlers.values():
            lines.append(f"  /{handler.command} - {handler.get_usage()}")

        lines.append("")
        lines.append("💡 提示：")
        lines.append("- 搜索结果是有效期5分钟")
        lines.append("- 报名/取消报名需要二次确认")

        return Response.text("\n".join(lines))
