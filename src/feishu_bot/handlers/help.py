"""/alive 指令处理器"""

from src.models import UserSession
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.help")


class HelpHandler(CommandHandler):
    """帮助指令"""

    @property
    def command(self) -> str:
        return "help"

    def get_usage(self) -> str:
        return "/help - 显示帮助信息"

    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /help 指令"""
        logger.info("执行 /help 指令")

        return "帮助信息\n\n" + \
            "/help 显示帮助信息\n" + \
            "/check 更新数据库并检查差异\n" + \
            "/valid 查看可报名活动\n" + \
            "/info 查看已报名信息\n" + \
            "/cancel 取消报名\n" + \
            "/search 搜索二课\n" + \
            "/join 报名二课\n" + \
            "/ignore 将活动加入不感兴趣列表\n" + \
            "/alive 查看系统状态\n"
