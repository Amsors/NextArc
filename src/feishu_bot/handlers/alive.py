"""/alive 指令处理器"""

from src.notifications import Response
from src.utils.formatter import format_status_message
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.alive")


class AliveHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "alive"

    def get_usage(self) -> str:
        return "/alive - 检查服务器是否正常运行"

    async def handle(self, args: list[str], session) -> Response:
        logger.info("执行 /alive 指令")

        if not self.check_dependencies():
            return Response.text("服务未完全初始化\n\n部分功能可能不可用")

        try:
            is_running = self._scanner.is_running()
            last_scan = self._scanner.get_last_scan_time()
            next_scan = self._scanner.get_next_scan_time()
            is_logged_in = self._auth_manager.is_logged_in()
            db_count = self._db_manager.get_db_count()

            ignore_count = 0
            interested_count = 0
            if self._user_preference_manager:
                ignore_count = await self._user_preference_manager.get_ignored_count()
                interested_count = await self._user_preference_manager.get_interested_count()

            status_text = format_status_message(
                is_running=is_running,
                last_scan=last_scan,
                next_scan=next_scan,
                is_logged_in=is_logged_in,
                db_count=db_count,
                ignore_count=ignore_count,
                interested_count=interested_count,
            )
            return Response.text(status_text)

        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return Response.error(str(e), context="获取状态")
