"""消息发送器"""

from typing import TYPE_CHECKING

from pyustc.young import SecondClass

from src.utils.formatter import build_activity_card, CardButtonConfig
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.formatter import CardButtonConfig

logger = get_logger("feishu.sender")

DEFAULT_MAX_ACTIVITIES_PER_CARD = 20


class MessageSender:
    """飞书消息发送器"""

    def __init__(self, bot=None):
        self._bot = bot

    def set_bot(self, bot):
        """设置机器人实例"""
        self._bot = bot

    async def send(self, content: str) -> bool:
        """发送文本消息"""
        if not self._bot:
            logger.error("未设置机器人实例，无法发送消息")
            return False

        return await self._bot.send_text(content)

    async def send_error(self, error: str, context: str = "") -> bool:
        """发送错误消息"""
        lines = ["操作失败"]

        if context:
            lines.append(f"上下文：{context}")

        lines.append(f"错误：{error}")

        return await self.send("\n".join(lines))

    async def send_success(self, message: str) -> bool:
        """发送成功消息"""
        return await self.send(f"成功 {message}")

    async def send_info(self, message: str) -> bool:
        """发送信息消息"""
        return await self.send(f"信息 {message}")

    async def send_card(self, card_content: dict) -> bool:
        """发送消息卡片"""
        if not self._bot:
            logger.error("未设置机器人实例，无法发送卡片")
            return False

        return await self._bot.send_card(card_content)

    async def send_activity_list_card(
            self,
            activities: list[SecondClass],
            title: str = "活动列表",
            button_config: "CardButtonConfig | None" = None
    ) -> bool:
        """
        发送活动列表卡片（带折叠面板）
        
        Args:
            activities: 活动列表
            title: 卡片标题
            button_config: 按钮配置，默认为None（使用默认配置）
        """
        if button_config is None:
            button_config = CardButtonConfig()

        if not activities:
            card_content = build_activity_card(activities, title, button_config=button_config)
            return await self.send_card(card_content)

        max_per_card = DEFAULT_MAX_ACTIVITIES_PER_CARD
        try:
            from src.config import get_settings
            settings = get_settings()
            max_per_card = settings.feishu.max_activities_per_card
        except Exception as e:
            logger.warning(f"获取配置失败，使用默认值 {DEFAULT_MAX_ACTIVITIES_PER_CARD}: {e}")

        if len(activities) <= max_per_card:
            card_content = build_activity_card(activities, title, button_config=button_config)
            return await self.send_card(card_content)

        # 分批发送
        total = len(activities)
        batches = (total + max_per_card - 1) // max_per_card
        logger.info(f"活动数量({total})超过限制({max_per_card})，将分{batches}条消息发送")

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
                start_index=start_index,
                button_config=button_config
            )

            success = await self.send_card(card_content)
            if not success:
                logger.error(f"第{batch_idx + 1}/{batches}批卡片发送失败")
                all_success = False

            # 分批发送之间添加短暂延迟，避免触发限流
            if batch_idx < batches - 1:
                import asyncio
                await asyncio.sleep(0.5)

        return all_success
