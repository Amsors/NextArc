"""飞书通知服务实现

基于 FeishuBot 的通知服务实现。
"""

from typing import TYPE_CHECKING

from src.utils.logger import get_logger
from .service import NotificationService

if TYPE_CHECKING:
    from src.feishu_bot.client import FeishuBot

logger = get_logger("notifications.feishu")


class FeishuNotificationService(NotificationService):
    """
    飞书通知服务实现

    通过 FeishuBot 发送文本和卡片消息。
    """

    def __init__(self, bot: "FeishuBot"):
        """
        初始化飞书通知服务

        Args:
            bot: FeishuBot 实例
        """
        self._bot = bot

    async def send_text(self, message: str) -> bool:
        """
        发送文本消息

        Args:
            message: 消息内容

        Returns:
            是否发送成功
        """
        if not self._bot or not self._bot.is_connected():
            logger.warning("飞书机器人未连接，无法发送文本消息")
            return False

        try:
            return await self._bot.send_text(message)
        except Exception as e:
            logger.error(f"发送飞书文本消息失败: {e}")
            return False

    async def send_card(self, card_content: dict) -> bool:
        """
        发送消息卡片

        Args:
            card_content: 卡片内容字典

        Returns:
            是否发送成功
        """
        if not self._bot or not self._bot.is_connected():
            logger.warning("飞书机器人未连接，无法发送卡片消息")
            return False

        try:
            return await self._bot.send_card(card_content)
        except Exception as e:
            logger.error(f"发送飞书卡片消息失败: {e}")
            return False

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._bot is not None and self._bot.is_connected()
