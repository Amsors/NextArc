"""通知响应对象"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ResponseType(Enum):
    """响应类型枚举"""
    TEXT = auto()
    CARD = auto()
    NONE = auto()  # 无响应（如静默处理）


@dataclass
class Response:
    """统一响应对象，支持文本消息和消息卡片"""
    type: ResponseType
    content: str | dict | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, content: str, **metadata) -> "Response":
        """创建文本响应"""
        return cls(type=ResponseType.TEXT, content=content, metadata=metadata)

    @classmethod
    def card(cls, card_content: dict, **metadata) -> "Response":
        """创建卡片响应"""
        return cls(type=ResponseType.CARD, content=card_content, metadata=metadata)

    @classmethod
    def none(cls) -> "Response":
        """创建无响应（用于无需回复的场景）"""
        return cls(type=ResponseType.NONE)

    @classmethod
    def activity_list(
            cls,
            activities: list,
            title: str = "活动列表",
            filters_applied: list[str] | None = None,
            button_config: "CardButtonConfig | None" = None,
            **metadata
    ) -> "Response":
        """
        创建活动列表卡片响应
        
        Args:
            activities: 活动列表
            title: 卡片标题
            filters_applied: 已应用的筛选器列表
            button_config: 按钮配置，默认为None（使用默认配置）
            **metadata: 额外元数据
        """
        from src.utils.formatter import build_activity_card, CardButtonConfig

        if button_config is None:
            button_config = CardButtonConfig()

        card_content = build_activity_card(activities, title, button_config=button_config)

        meta = {
            "activities": activities,
            "title": title,
            "filters_applied": filters_applied or [],
            "button_config": button_config,
            **metadata
        }

        return cls(type=ResponseType.CARD, content=card_content, metadata=meta)

    @classmethod
    def enrolled_list(
            cls,
            activities: list,
            title: str = "已报名活动",
            filters_applied: list[str] | None = None,
            **metadata
    ) -> "Response":
        """
        创建已报名活动列表卡片响应（显示取消报名按钮）
        
        Args:
            activities: 已报名活动列表
            title: 卡片标题
            filters_applied: 已应用的筛选器列表
            **metadata: 额外元数据
        """
        from src.utils.formatter import CardButtonConfig

        # 已报名活动的按钮配置：显示取消报名按钮，不显示不感兴趣和去报名按钮
        button_config = CardButtonConfig(
            show_ignore_button=False,
            show_join_button=False,
            show_cancel_button=True,
            show_children_button=True
        )

        return cls.activity_list(
            activities=activities,
            title=title,
            filters_applied=filters_applied,
            button_config=button_config,
            **metadata
        )

    @classmethod
    def error(cls, message: str, context: str = "") -> "Response":
        """创建错误响应"""
        lines = ["操作失败"]
        if context:
            lines.append(f"上下文：{context}")
        lines.append(f"错误：{message}")
        return cls.text("\n".join(lines), error=True)

    @classmethod
    def success(cls, message: str) -> "Response":
        """创建成功响应"""
        return cls.text(f"成功 {message}", success=True)

    @classmethod
    def info(cls, message: str) -> "Response":
        """创建信息响应"""
        return cls.text(f"信息 {message}", info=True)

    def is_empty(self) -> bool:
        """检查响应是否为空"""
        if self.type == ResponseType.NONE:
            return True
        if self.content is None:
            return True
        if isinstance(self.content, str) and not self.content.strip():
            return True
        return False

    def get_text(self) -> str | None:
        """获取文本内容（如果不是文本类型则返回 None）"""
        if self.type == ResponseType.TEXT and isinstance(self.content, str):
            return self.content
        return None

    def get_card(self) -> dict | None:
        """获取卡片内容（如果不是卡片类型则返回 None）"""
        if self.type == ResponseType.CARD and isinstance(self.content, dict):
            return self.content
        return None
