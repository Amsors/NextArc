"""指令处理器基类"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core import ActivityScanner, AuthManager, DatabaseManager
    from src.core.services import ActivityQueryService, ActivityUpdateService, EnrollmentService

logger = get_logger("feishu.handler")


class CommandHandler(ABC):
    _scanner: "ActivityScanner" = None
    _auth_manager: "AuthManager" = None
    _db_manager: "DatabaseManager" = None
    _activity_query_service: "ActivityQueryService" = None
    _activity_update_service: "ActivityUpdateService" = None
    _enrollment_service: "EnrollmentService" = None

    @classmethod
    def set_dependencies(
            cls,
            scanner: "ActivityScanner",
            auth_manager: "AuthManager",
            db_manager: "DatabaseManager",
            activity_query_service: "ActivityQueryService | None" = None,
            activity_update_service: "ActivityUpdateService | None" = None,
            enrollment_service: "EnrollmentService | None" = None,
    ):
        cls._scanner = scanner
        cls._auth_manager = auth_manager
        cls._db_manager = db_manager
        cls._activity_query_service = activity_query_service
        cls._activity_update_service = activity_update_service
        cls._enrollment_service = enrollment_service

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
