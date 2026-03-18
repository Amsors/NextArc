"""登录态管理器"""

from typing import Optional

from pyustc import CASClient, YouthService

from src.utils.logger import get_logger

logger = get_logger("auth")


class AuthManager:
    """
    管理 CAS 和 YouthService 登录态
    
    注意：YouthService 使用了 ContextVar，必须在同一个异步上下文中使用。
    本类提供单次会话执行功能，避免上下文切换问题。
    """
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._last_login_time: Optional[float] = None
    
    def create_session_once(self):
        """
        创建一次性会话上下文管理器
        
        使用方式：
            async with auth_manager.create_session_once() as service:
                # 使用 service 进行操作
                await SecondClass.find(...)
        
        Returns:
            AuthSessionContext 上下文管理器（可直接用于 async with）
        """
        return AuthSessionContext(self.username, self.password)
    
    def is_logged_in(self) -> bool:
        """检查是否有登录记录"""
        return self._last_login_time is not None


class AuthSessionContext:
    """
    认证会话上下文管理器
    
    用于 async with 语句，确保会话正确创建和关闭
    """
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._client = None
        self._service = None
        self._client_obj = None
        self._service_obj = None
    
    async def __aenter__(self):
        """进入上下文，创建会话"""
        logger.debug(f"正在创建认证会话...")
        
        # 创建 CAS 客户端并登录
        self._client = CASClient.login_by_pwd(self.username, self.password)
        self._client_obj = await self._client.__aenter__()
        
        # 创建 YouthService 并登录
        self._service = YouthService()
        self._service_obj = await self._service.__aenter__()
        await self._service_obj.login(self._client_obj)
        
        logger.debug("认证会话创建成功")
        return self._service_obj
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，关闭会话"""
        logger.debug("正在关闭认证会话...")
        
        # 先关闭 YouthService
        if self._service:
            try:
                await self._service.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"关闭 YouthService 时出错: {e}")
            finally:
                self._service = None
                self._service_obj = None
        
        # 再关闭 CASClient
        if self._client:
            try:
                await self._client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"关闭 CASClient 时出错: {e}")
            finally:
                self._client = None
                self._client_obj = None
        
        logger.debug("认证会话已关闭")
