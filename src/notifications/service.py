"""通知服务抽象接口

定义统一的通知服务接口，支持多种实现（飞书、控制台、邮件等）。
"""

from abc import ABC, abstractmethod

from .response import Response, ResponseType


class NotificationService(ABC):
    """
    通知服务抽象接口

    所有通知渠道的实现都需要继承此类。

    示例:
        class FeishuNotificationService(NotificationService):
            async def send_text(self, message: str) -> bool:
                # 实现飞书文本发送
                pass

            async def send_card(self, card_content: dict) -> bool:
                # 实现飞书卡片发送
                pass
    """

    @abstractmethod
    async def send_text(self, message: str) -> bool:
        """
        发送文本消息

        Args:
            message: 消息内容

        Returns:
            是否发送成功
        """
        pass

    @abstractmethod
    async def send_card(self, card_content: dict) -> bool:
        """
        发送消息卡片

        Args:
            card_content: 卡片内容字典，符合飞书消息卡片 JSON 结构

        Returns:
            是否发送成功
        """
        pass

    async def send_response(self, response: Response) -> bool:
        """
        统一发送 Response 对象

        根据 Response 类型自动选择发送方式。

        Args:
            response: 响应对象

        Returns:
            是否发送成功
        """
        if response.is_empty():
            return True

        if response.type == ResponseType.TEXT:
            return await self.send_text(response.content)
        elif response.type == ResponseType.CARD:
            return await self.send_card(response.content)

        return True

    async def send_error(self, error: str, context: str = "") -> bool:
        """发送错误消息"""
        lines = ["操作失败"]
        if context:
            lines.append(f"上下文：{context}")
        lines.append(f"错误：{error}")
        return await self.send_text("\n".join(lines))

    async def send_success(self, message: str) -> bool:
        """发送成功消息"""
        return await self.send_text(f"成功 {message}")

    async def send_info(self, message: str) -> bool:
        """发送信息消息"""
        return await self.send_text(f"信息 {message}")
