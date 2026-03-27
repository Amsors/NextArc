"""通知服务抽象接口

定义统一的通知服务接口，支持多种实现（飞书、控制台、邮件等）。
"""

from abc import ABC, abstractmethod

from .response import Response, ResponseType

# 默认每条消息最多显示的活动数
DEFAULT_MAX_ACTIVITIES_PER_CARD = 20


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
        对于活动列表卡片，会自动分批发送以避免超出飞书消息长度限制。

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
            # 检查是否是活动列表卡片（通过 metadata 中的 activities 字段判断）
            activities = response.metadata.get("activities")
            if activities is not None and isinstance(activities, list):
                # 使用分批发送逻辑
                title = response.metadata.get("title", "活动列表")
                return await self.send_activity_list_card(activities, title)
            else:
                # 普通卡片，直接发送
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

    async def send_activity_list_card(
            self,
            activities: list,
            title: str = "活动列表",
            ignored_ids: set[str] | None = None
    ) -> bool:
        """
        发送活动列表卡片（带折叠面板）
        
        当活动数量超过配置的限制时，会自动分多条消息发送，并保持序号连续。
        默认实现直接构建单条卡片，子类可以覆盖以实现分批发送。
        
        Args:
            activities: 活动列表（SecondClass 对象列表）
            title: 卡片标题
            ignored_ids: 已被忽略的活动ID集合
            
        Returns:
            是否发送成功
        """
        from src.utils.formatter import build_activity_card

        if not activities:
            card_content = build_activity_card(activities, title, ignored_ids)
            return await self.send_card(card_content)

        # 获取配置中的最大活动数限制
        max_per_card = DEFAULT_MAX_ACTIVITIES_PER_CARD
        try:
            from src.config import get_settings
            settings = get_settings()
            max_per_card = settings.feishu.max_activities_per_card
        except Exception:
            pass  # 使用默认值

        # 如果活动数量未超过限制，直接发送
        if len(activities) <= max_per_card:
            card_content = build_activity_card(activities, title, ignored_ids)
            return await self.send_card(card_content)

        # 分批发送
        total = len(activities)
        batches = (total + max_per_card - 1) // max_per_card

        all_success = True
        for batch_idx in range(batches):
            start = batch_idx * max_per_card
            end = min(start + max_per_card, total)
            batch_activities = activities[start:end]
            start_index = start + 1

            if batches > 1:
                batch_title = f"{title}（{batch_idx + 1}/{batches}）"
            else:
                batch_title = title

            card_content = build_activity_card(
                batch_activities,
                batch_title,
                ignored_ids,
                start_index=start_index
            )

            success = await self.send_card(card_content)
            if not success:
                all_success = False

            # 分批发送之间添加短暂延迟
            if batch_idx < batches - 1:
                import asyncio
                await asyncio.sleep(0.5)

        return all_success
