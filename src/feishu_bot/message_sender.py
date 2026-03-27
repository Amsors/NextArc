"""消息发送器"""

from pyustc.young import SecondClass

from src.utils.formatter import build_activity_card
from src.utils.logger import get_logger

logger = get_logger("feishu.sender")

# 默认每条消息最多显示的活动数
DEFAULT_MAX_ACTIVITIES_PER_CARD = 20


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
        lines = ["操作失败"]

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
        return await self.send(f"成功 {message}")

    async def send_info(self, message: str) -> bool:
        """
        发送信息消息
        
        Args:
            message: 信息内容
            
        Returns:
            是否发送成功
        """
        return await self.send(f"信息 {message}")

    async def send_card(self, card_content: dict) -> bool:
        """
        发送消息卡片
        
        Args:
            card_content: 卡片内容字典
            
        Returns:
            是否发送成功
        """
        if not self._bot:
            logger.error("未设置机器人实例，无法发送卡片")
            return False

        return await self._bot.send_card(card_content)

    async def send_activity_list_card(self, activities: list[SecondClass], title: str = "活动列表") -> bool:
        """
        发送活动列表卡片（带折叠面板）
        
        当活动数量超过配置的限制时，会自动分多条消息发送，并保持序号连续。
        
        Args:
            activities: 活动列表
            title: 卡片标题
            
        Returns:
            是否发送成功（所有分批消息都发送成功才返回 True）
        """
        if not activities:
            # 没有活动，直接发送空卡片
            card_content = build_activity_card(activities, title)
            return await self.send_card(card_content)

        # 获取配置中的最大活动数限制
        max_per_card = DEFAULT_MAX_ACTIVITIES_PER_CARD
        try:
            from src.config import get_settings
            settings = get_settings()
            max_per_card = settings.feishu.max_activities_per_card
        except Exception as e:
            logger.warning(f"获取配置失败，使用默认值 {DEFAULT_MAX_ACTIVITIES_PER_CARD}: {e}")

        # 如果活动数量未超过限制，直接发送
        if len(activities) <= max_per_card:
            card_content = build_activity_card(activities, title)
            return await self.send_card(card_content)

        # 分批发送
        total = len(activities)
        batches = (total + max_per_card - 1) // max_per_card  # 向上取整
        logger.info(f"活动数量({total})超过限制({max_per_card})，将分{batches}条消息发送")

        all_success = True
        for batch_idx in range(batches):
            start = batch_idx * max_per_card
            end = min(start + max_per_card, total)
            batch_activities = activities[start:end]
            start_index = start + 1  # 序号从1开始

            # 分批标题：主标题 + 分批信息
            if batches > 1:
                batch_title = f"{title}（{batch_idx + 1}/{batches}）"
            else:
                batch_title = title

            card_content = build_activity_card(
                batch_activities,
                batch_title,
                start_index=start_index
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
