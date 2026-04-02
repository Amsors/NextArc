"""登录态管理器"""

from typing import Optional

from pyustc import CASClient, YouthService

from src.utils.logger import get_logger

logger = get_logger("auth")


class AuthManager:
    """管理 CAS 和 YouthService 登录态
    
    注意：YouthService 使用了 ContextVar，必须在同一个异步上下文中使用。
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._last_login_time: Optional[float] = None

    def create_session_once(self):
        """创建一次性会话上下文管理器"""
        return AuthSessionContext(self.username, self.password)

    def is_logged_in(self) -> bool:
        return self._last_login_time is not None


class AuthSessionContext:
    """认证会话上下文管理器"""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._client = None
        self._service = None
        self._client_obj = None
        self._service_obj = None

    async def __aenter__(self):
        logger.debug(f"正在创建认证会话...")

        self._client = CASClient.login_by_pwd(self.username, self.password)
        self._client_obj = await self._client.__aenter__()

        self._service = YouthService()
        self._service_obj = await self._service.__aenter__()
        await self._service_obj.login(self._client_obj)

        logger.debug("认证会话创建成功")
        return self._service_obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.debug("正在关闭认证会话...")

        if self._service:
            try:
                await self._service.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"关闭 YouthService 时出错: {e}")
            finally:
                self._service = None
                self._service_obj = None

        if self._client:
            try:
                await self._client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"关闭 CASClient 时出错: {e}")
            finally:
                self._client = None
                self._client_obj = None

        logger.debug("认证会话已关闭")
