"""通知响应对象"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from src.feishu_bot.card_builder import ActivityListCardRequest, CardButtonConfig


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
            ignored_ids: set[str] | None = None,
            button_config: "CardButtonConfig | None" = None,
            ai_reasons: dict[str, str] | None = None,
            overlap_reasons: dict[str, str] | None = None,
            **metadata
    ) -> "Response":
        """创建活动列表卡片响应"""
        if button_config is None:
            button_config = CardButtonConfig()

        activity_card_request = ActivityListCardRequest(
            activities=activities,
            title=title,
            ignored_ids=ignored_ids or set(),
            button_config=button_config,
            ai_reasons=ai_reasons or {},
            overlap_reasons=overlap_reasons or {},
        )

        meta = {
            "activity_card_request": activity_card_request,
            "filters_applied": filters_applied or [],
            **metadata
        }

        return cls(type=ResponseType.CARD, content={"kind": "activity_list"}, metadata=meta)

    @classmethod
    def enrolled_list(
            cls,
            activities: list,
            title: str = "已报名活动",
            filters_applied: list[str] | None = None,
            **metadata
    ) -> "Response":
        """创建已报名活动列表卡片响应（显示取消报名按钮）"""
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
