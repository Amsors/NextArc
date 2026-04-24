"""指令处理器基类"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core import ActivityScanner, AuthManager, DatabaseManager
    from src.core.services import ActivityQueryService, ActivityUpdateService, EnrollmentService
    from src.app import AppContext
    from src.core.user_preference_manager import UserPreferenceManager

logger = get_logger("feishu.handler")


class CommandHandler(ABC):
    def __init__(self, app_context: "AppContext | None" = None):
        self.app_context = app_context

    @property
    def _scanner(self) -> "ActivityScanner | None":
        return self._get_context_attr("scanner")

    @property
    def _auth_manager(self) -> "AuthManager | None":
        return self._get_context_attr("auth_manager")

    @property
    def _db_manager(self) -> "DatabaseManager | None":
        return self._get_context_attr("db_manager")

    @property
    def _activity_query_service(self) -> "ActivityQueryService | None":
        return self._get_context_attr("activity_query_service")

    @property
    def _activity_update_service(self) -> "ActivityUpdateService | None":
        return self._get_context_attr("activity_update_service")

    @property
    def _enrollment_service(self) -> "EnrollmentService | None":
        return self._get_context_attr("enrollment_service")

    @property
    def _user_preference_manager(self) -> "UserPreferenceManager | None":
        return self._get_context_attr("preference_manager")

    @property
    def _ignore_manager(self) -> "UserPreferenceManager | None":
        return self._user_preference_manager

    @property
    def _settings(self) -> Any:
        return self._get_context_attr("settings")

    def _get_context_attr(self, name: str) -> Any:
        if self.app_context is None:
            return None
        return getattr(self.app_context, name, None)

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
