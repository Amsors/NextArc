"""通知服务抽象接口"""

from abc import ABC, abstractmethod

from .response import Response, ResponseType

DEFAULT_MAX_ACTIVITIES_PER_CARD = 20


class NotificationService(ABC):
    """通知服务抽象接口，所有通知渠道的实现都需要继承此类"""

    @abstractmethod
    async def send_text(self, message: str) -> bool:
        """发送文本消息"""
        pass

    @abstractmethod
    async def send_card(self, card_content: dict) -> bool:
        """发送消息卡片"""
        pass

    async def send_response(self, response: Response) -> bool:
        """根据 Response 类型自动选择发送方式"""
        if response.is_empty():
            return True

        if response.type == ResponseType.TEXT:
            return await self.send_text(response.content)
        elif response.type == ResponseType.CARD:
            activities = response.metadata.get("activities")
            if activities is not None and isinstance(activities, list):
                title = response.metadata.get("title", "活动列表")
                return await self.send_activity_list_card(activities, title)
            else:
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
        发送活动列表卡片

        当活动数量超过限制时自动分批发送，保持序号连续。
        """
        from src.utils.formatter import build_activity_card

        if not activities:
            card_content = build_activity_card(activities, title, ignored_ids)
            return await self.send_card(card_content)

        max_per_card = DEFAULT_MAX_ACTIVITIES_PER_CARD
        try:
            from src.config import get_settings
            settings = get_settings()
            max_per_card = settings.feishu.max_activities_per_card
        except Exception:
            pass

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

            batch_title = f"{title}（{batch_idx + 1}/{batches}）" if batches > 1 else title

            card_content = build_activity_card(
                batch_activities,
                batch_title,
                ignored_ids,
                start_index=start_index
            )

            success = await self.send_card(card_content)
            if not success:
                all_success = False

            if batch_idx < batches - 1:
                import asyncio
                await asyncio.sleep(0.5)

        return all_success
