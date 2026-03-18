"""/alive 指令处理器"""

from datetime import datetime

from src.models import UserSession
from src.utils.formatter import format_status_message
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.alive")


class AliveHandler(CommandHandler):
    """检查服务状态指令"""
    
    @property
    def command(self) -> str:
        return "alive"
    
    def get_usage(self) -> str:
        return "/alive - 检查服务器是否正常运行"
    
    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /alive 指令"""
        logger.info("执行 /alive 指令")
        
        if not self.check_dependencies():
            return "⚠️ 服务未完全初始化\n\n部分功能可能不可用"
        
        try:
            # 收集状态信息
            is_running = self._scanner.is_running()
            last_scan = self._scanner.get_last_scan_time()
            next_scan = self._scanner.get_next_scan_time()
            is_logged_in = self._auth_manager.is_logged_in()
            db_count = self._db_manager.get_db_count()
            
            return format_status_message(
                is_running=is_running,
                last_scan=last_scan,
                next_scan=next_scan,
                is_logged_in=is_logged_in,
                db_count=db_count,
            )
            
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return f"❌ 获取状态失败：{str(e)}"
