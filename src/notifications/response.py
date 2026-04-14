"""通知响应对象"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ResponseType(Enum):
    TEXT = auto()
    CARD = auto()
    NONE = auto()


@dataclass
class Response:
    """统一响应对象，支持文本消息和消息卡片"""
    type: ResponseType
    content: str | dict | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, content: str, **metadata) -> "Response":
        return cls(type=ResponseType.TEXT, content=content, metadata=metadata)

    @classmethod
    def card(cls, card_content: dict, **metadata) -> "Response":
        return cls(type=ResponseType.CARD, content=card_content, metadata=metadata)

    @classmethod
    def none(cls) -> "Response":
        return cls(type=ResponseType.NONE)

    @classmethod
    def activity_list(
            cls,
            activities: list,
            title: str = "活动列表",
            filters_applied: list[str] | None = None,
            button_config: "CardButtonConfig | None" = None,
            ai_reasons: dict[str, str] | None = None,
            **metadata  # TODO 检查此处额外元数据
    ) -> "Response":
        """创建活动列表卡片响应"""
        from src.utils.formatter import build_activity_card, CardButtonConfig

        if button_config is None:
            button_config = CardButtonConfig()

        card_content = build_activity_card(activities, title, button_config=button_config, ai_reasons=ai_reasons)

        meta = {
            "activities": activities,
            "title": title,
            "filters_applied": filters_applied or [],
            "button_config": button_config,
            "ai_reasons": ai_reasons,
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
        """创建已报名活动列表卡片响应（显示取消报名按钮）"""
        from src.utils.formatter import CardButtonConfig

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
        lines = ["操作失败"]
        if context:
            lines.append(f"上下文：{context}")
        lines.append(f"错误：{message}")
        return cls.text("\n".join(lines), error=True)

    @classmethod
    def success(cls, message: str) -> "Response":
        return cls.text(f"成功 {message}", success=True)

    @classmethod
    def info(cls, message: str) -> "Response":
        return cls.text(f"信息 {message}", info=True)

    def is_empty(self) -> bool:
        if self.type == ResponseType.NONE:
            return True
        if self.content is None:
            return True
        if isinstance(self.content, str) and not self.content.strip():
            return True
        return False

    def get_text(self) -> str | None:
        if self.type == ResponseType.TEXT and isinstance(self.content, str):
            return self.content
        return None

    def get_card(self) -> dict | None:
        if self.type == ResponseType.CARD and isinstance(self.content, dict):
            return self.content
        return None
