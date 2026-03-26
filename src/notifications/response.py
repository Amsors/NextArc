"""通知响应对象

统一处理所有类型的通知响应，支持文本和卡片格式。
"""

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
    """
    统一响应对象

    用于 Handler 返回需要发送给用户的内容，
    支持文本消息和消息卡片两种格式。

    示例:
        # 返回文本
        return Response.text("Hello World")

        # 返回卡片
        return Response.card(card_content_dict)

        # 返回活动列表卡片
        return Response.activity_list(activities, title="活动列表")
    """
    type: ResponseType
    content: str | dict | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, content: str, **metadata) -> "Response":
        """
        创建文本响应

        Args:
            content: 文本内容
            **metadata: 额外元数据
        """
        return cls(type=ResponseType.TEXT, content=content, metadata=metadata)

    @classmethod
    def card(cls, card_content: dict, **metadata) -> "Response":
        """
        创建卡片响应

        Args:
            card_content: 飞书消息卡片内容字典
            **metadata: 额外元数据
        """
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
            **metadata
    ) -> "Response":
        """
        创建活动列表卡片响应

        Args:
            activities: SecondClass 对象列表
            title: 卡片标题
            filters_applied: 应用的筛选器信息列表
            **metadata: 额外元数据
        """
        from src.utils.formatter import build_activity_card

        card_content = build_activity_card(activities, title)

        meta = {
            "activities": activities,
            "title": title,
            "filters_applied": filters_applied or [],
            **metadata
        }

        return cls(type=ResponseType.CARD, content=card_content, metadata=meta)

    @classmethod
    def error(cls, message: str, context: str = "") -> "Response":
        """
        创建错误响应

        Args:
            message: 错误信息
            context: 错误上下文
        """
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
