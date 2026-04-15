"""指令处理器基类"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core import ActivityScanner, AuthManager, DatabaseManager

logger = get_logger("feishu.handler")


class CommandHandler(ABC):
    _scanner: "ActivityScanner" = None
    _auth_manager: "AuthManager" = None
    _db_manager: "DatabaseManager" = None
    _bot = None

    @classmethod
    def set_dependencies(
            cls,
            scanner: "ActivityScanner",
            auth_manager: "AuthManager",
            db_manager: "DatabaseManager",
    ):
        cls._scanner = scanner
        cls._auth_manager = auth_manager
        cls._db_manager = db_manager

    @classmethod
    def set_bot(cls, bot):
        cls._bot = bot

    @property
    @abstractmethod
    def command(self) -> str:
        pass

    @abstractmethod
    async def handle(self, args: list[str], session: UserSession) -> Response:
        pass

    def get_usage(self) -> str:
        return f"/{self.command}"

    def check_dependencies(self) -> bool:
        if not self._scanner:
            logger.error(f"处理器 {self.command} 未设置 scanner 依赖")
            return False
        return True
