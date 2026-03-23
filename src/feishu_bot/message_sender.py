"""消息发送器"""

from src.utils.logger import get_logger

logger = get_logger("feishu.sender")


class MessageSender:
    """
    飞书消息发送器
    
    封装消息发送功能，便于在不同模块中复用
    """

    def __init__(self, bot=None):
        self._bot = bot

    def set_bot(self, bot):
        """设置机器人实例"""
        self._bot = bot

    async def send(self, content: str) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            
        Returns:
            是否发送成功
        """
        if not self._bot:
            logger.error("未设置机器人实例，无法发送消息")
            return False

        return await self._bot.send_text(content)

    async def send_error(self, error: str, context: str = "") -> bool:
        """
        发送错误消息
        
        Args:
            error: 错误信息
            context: 错误上下文
            
        Returns:
            是否发送成功
        """
        lines = ["❌ 操作失败"]

        if context:
            lines.append(f"上下文：{context}")

        lines.append(f"错误：{error}")

        return await self.send("\n".join(lines))

    async def send_success(self, message: str) -> bool:
        """
        发送成功消息
        
        Args:
            message: 成功信息
            
        Returns:
            是否发送成功
        """
        return await self.send(f"✅ {message}")

    async def send_info(self, message: str) -> bool:
        """
        发送信息消息
        
        Args:
            message: 信息内容
            
        Returns:
            是否发送成功
        """
        return await self.send(f"ℹ️ {message}")
