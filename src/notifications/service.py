"""通知服务抽象接口"""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.feishu_bot.card_builder import (
    ActivityCardBuilder,
    ActivityCardDisplayConfig,
    ActivityListCardRequest,
)
from .response import Response, ResponseType

if TYPE_CHECKING:
    from src.feishu_bot.card_builder import CardButtonConfig

DEFAULT_MAX_ACTIVITIES_PER_CARD = 20
CARD_BATCH_SEND_INTERVAL_SECONDS = 0.5
CardDisplayConfig = ActivityCardDisplayConfig


class NotificationService(ABC):
    """通知服务抽象接口，所有通知渠道的实现都需要继承此类"""

    def __init__(
        self,
        card_config: CardDisplayConfig | None = None,
        card_builder: ActivityCardBuilder | None = None,
    ):
        self.card_config = card_config or CardDisplayConfig()
        self.card_builder = card_builder or ActivityCardBuilder()

    @abstractmethod
    async def send_text(self, message: str) -> bool:
        pass

    @abstractmethod
    async def send_card(self, card_content: dict) -> bool:
        pass

    async def send_response(self, response: Response) -> bool:
        """根据 Response 类型自动选择发送方式"""
        if response.is_empty():
            return True

        if response.type == ResponseType.TEXT:
            return await self.send_text(response.content)
        elif response.type == ResponseType.CARD:
            activity_card_request = response.metadata.get("activity_card_request")
            if isinstance(activity_card_request, ActivityListCardRequest):
                return await self.send_activity_list_card(activity_card_request)

            if isinstance(response.content, dict):
                return await self.send_card(response.content)

        return True

    async def send_error(self, error: str, context: str = "") -> bool:
        lines = ["操作失败"]
        if context:
            lines.append(f"上下文：{context}")
        lines.append(f"错误：{error}")
        return await self.send_text("\n".join(lines))

    async def send_success(self, message: str) -> bool:
        return await self.send_text(f"成功 {message}")

    async def send_info(self, message: str) -> bool:
        return await self.send_text(f"信息 {message}")

    async def send_activity_list_card(
            self,
            activities: list | ActivityListCardRequest,
            title: str = "活动列表",
            ignored_ids: set[str] | None = None,
            button_config: "CardButtonConfig | None" = None,
            ai_reasons: dict[str, str] | None = None,
            overlap_reasons: dict[str, str] | None = None,
    ) -> bool:
        """发送活动列表卡片，当活动数量超过限制时自动分批发送"""
        if isinstance(activities, ActivityListCardRequest):
            request = activities
        else:
            request = ActivityListCardRequest(
                activities=activities,
                title=title,
                ignored_ids=ignored_ids or set(),
                button_config=button_config,
                ai_reasons=ai_reasons or {},
                overlap_reasons=overlap_reasons or {},
            )

        cards = self.card_builder.build_activity_cards(request, self.card_config)

        all_success = True
        for index, card_content in enumerate(cards):
            success = await self.send_card(card_content)
            if not success:
                all_success = False

            if index < len(cards) - 1:
                await asyncio.sleep(CARD_BATCH_SEND_INTERVAL_SECONDS)

        return all_success
