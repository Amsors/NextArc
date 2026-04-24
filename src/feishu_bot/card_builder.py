"""飞书消息卡片构建器。"""

from dataclasses import dataclass, field, replace

from pyustc.young import ParticipationForm, SecondClass

from src.models.secondclass_view import (
    get_apply_progress,
    get_conceive_text,
    get_department_name,
    get_description_text,
    get_display_time,
    get_labels_text,
    get_module_name,
    get_participation_form,
    get_place_info,
    get_status_text,
)
from src.utils.logger import get_logger

logger = get_logger("feishu.card_builder")

DEFAULT_MAX_ACTIVITIES_PER_CARD = 20


@dataclass(frozen=True)
class ActivityCardDisplayConfig:
    """活动列表卡片分页配置。"""

    max_activities_per_card: int = DEFAULT_MAX_ACTIVITIES_PER_CARD


@dataclass
class CardButtonConfig:
    """活动卡片按钮配置。"""

    show_ignore_button: bool = True
    show_interested_button: bool = True
    show_join_button: bool = True
    show_cancel_button: bool = False
    show_children_button: bool = True
    is_ignored: bool = False

    def get_buttons(self, act: SecondClass) -> list[dict]:
        """根据配置生成按钮列表。"""

        buttons = []

        if self.show_interested_button:
            buttons.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "感兴趣"},
                    "type": "default",
                    "value": {
                        "action": "toggle_interested",
                        "activity_id": act.id,
                        "activity_name": act.name,
                    },
                }
            )

        if self.show_ignore_button:
            ignore_button_text = "已忽略" if self.is_ignored else "不感兴趣"
            ignore_button_type = "default" if self.is_ignored else "danger"
            buttons.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": ignore_button_text},
                    "type": ignore_button_type,
                    "value": {
                        "action": "toggle_ignore",
                        "activity_id": act.id,
                        "activity_name": act.name,
                    },
                }
            )

        if self.show_cancel_button:
            buttons.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "取消报名"},
                    "type": "danger",
                    "value": {
                        "action": "cancel",
                        "activity_id": act.id,
                        "activity_name": act.name,
                    },
                }
            )

        if act.is_series:
            if self.show_children_button:
                buttons.append(
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看子活动"},
                        "type": "primary",
                        "value": {
                            "action": "view_children",
                            "activity_id": act.id,
                            "activity_name": act.name,
                        },
                    }
                )
        elif self.show_join_button:
            buttons.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "去报名"},
                    "type": "primary",
                    "value": {
                        "action": "join",
                        "activity_id": act.id,
                        "activity_name": act.name,
                    },
                }
            )

        return buttons


@dataclass
class ActivityListCardRequest:
    """活动列表卡片构建请求。"""

    activities: list[SecondClass]
    title: str = "活动列表"
    ignored_ids: set[str] = field(default_factory=set)
    start_index: int = 1
    button_config: CardButtonConfig | None = None
    ai_reasons: dict[str, str] = field(default_factory=dict)
    overlap_reasons: dict[str, str] = field(default_factory=dict)


class ActivityCardBuilder:
    """构建飞书活动列表卡片。"""

    def build_activity_cards(
        self,
        request: ActivityListCardRequest,
        display_config: ActivityCardDisplayConfig,
    ) -> list[dict]:
        """按分页配置构建一个或多个活动列表卡片。"""

        if not request.activities:
            return [self.build_activity_card(request)]

        max_per_card = max(1, display_config.max_activities_per_card)
        if len(request.activities) <= max_per_card:
            return [self.build_activity_card(request)]

        total = len(request.activities)
        batches = (total + max_per_card - 1) // max_per_card
        cards = []
        for batch_idx in range(batches):
            start = batch_idx * max_per_card
            end = min(start + max_per_card, total)
            batch_title = f"{request.title}（{batch_idx + 1}/{batches}）"
            batch_request = replace(
                request,
                activities=request.activities[start:end],
                title=batch_title,
                start_index=request.start_index + start,
            )
            cards.append(self.build_activity_card(batch_request))

        return cards

    def build_activity_card(self, request: ActivityListCardRequest) -> dict:
        """构建单张活动列表卡片。"""

        ai_reasons = request.ai_reasons or {}
        overlap_reasons = request.overlap_reasons or {}
        ignored_ids = request.ignored_ids or set()

        logger.debug(
            "build_activity_card: activities=%s, ai_reasons_keys=%s, overlap_reasons_keys=%s",
            len(request.activities),
            list(ai_reasons.keys()),
            list(overlap_reasons.keys()),
        )

        if not request.activities:
            return {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"{request.title}"},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "plain_text", "content": "暂无活动"},
                    }
                ],
            }

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"共找到 **{len(request.activities)}** 个活动",
                },
            },
            {"tag": "hr"},
        ]

        for i, act in enumerate(request.activities, request.start_index):
            is_ignored = act.id in ignored_ids
            if request.button_config is None:
                act_button_config = CardButtonConfig()
            else:
                act_button_config = replace(request.button_config, is_ignored=is_ignored)

            elements.append(
                _build_activity_collapsible_panel(
                    act,
                    i,
                    act_button_config,
                    ai_reason=ai_reasons.get(act.id),
                    overlap_reason=overlap_reasons.get(act.id),
                )
            )

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{request.title}"},
                "template": "blue",
            },
            "elements": elements,
        }


def _build_activity_collapsible_panel(
    act: SecondClass,
    index: int,
    button_config: CardButtonConfig | None = None,
    ai_reason: str | None = None,
    overlap_reason: str | None = None,
) -> dict:
    """为单个活动构建折叠面板。"""

    if button_config is None:
        button_config = CardButtonConfig()

    activity_type = "系列活动" if act.is_series else "单次活动"
    if overlap_reason:
        if act.participation_form == ParticipationForm.SUBMIT_WORKS:
            header_title = f"[{index}] 【重,提交作品】{act.name} ({activity_type})"
        else:
            header_title = f"[{index}] 【重】{act.name} ({activity_type})"
    else:
        header_title = f"[{index}] {act.name} ({activity_type})"

    detail_elements = [
        {
            "tag": "markdown",
            "content": f"**举办**\n{get_display_time(act, 'hold_time')}",
        }
    ]
    if not act.is_series:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**报名**\n{get_display_time(act, 'apply_time')}",
            }
        )
    detail_elements.extend(
        [
            {
                "tag": "markdown",
                "content": f"**模块**: {get_module_name(act)}",
            },
            {
                "tag": "markdown",
                "content": f"**组织单位**: {get_department_name(act)}",
            },
            {
                "tag": "markdown",
                "content": f"**地点**: {get_place_info(act)}",
            },
        ]
    )

    participation_form = get_participation_form(act)
    if participation_form:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**参与形式**: {participation_form}",
            }
        )

    if act.is_series:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**状态：** {get_status_text(act)}",
            }
        )
    else:
        detail_elements.extend(
            [
                {
                    "tag": "markdown",
                    "content": f"**状态**: {get_status_text(act)}",
                },
                {
                    "tag": "markdown",
                    "content": f"**学时**: {act.valid_hour or '未知'}",
                },
                {
                    "tag": "markdown",
                    "content": f"**报名**: {get_apply_progress(act)}",
                },
            ]
        )

    detail_elements.extend(
        [
            {
                "tag": "markdown",
                "content": f"**✏️ 活动构想**\n{get_conceive_text(act)}",
            },
            {
                "tag": "markdown",
                "content": f"**📚️ 活动描述**\n{get_description_text(act)}",
            },
        ]
    )

    labels = get_labels_text(act)
    if labels and labels != "无":
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**标签：** {labels}",
            }
        )

    if overlap_reason:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**⚠️ 时间重叠**\n{overlap_reason}",
            }
        )

    if ai_reason:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**🤖 AI 判断理由**\n{ai_reason}",
            }
        )

    detail_elements.append({"tag": "hr"})

    button_elements = button_config.get_buttons(act)
    if button_elements:
        detail_elements.append(
            {
                "tag": "action",
                "actions": button_elements,
            }
        )

    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "background_color": "grey",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": header_title,
            },
            "icon": {
                "tag": "standard_icon",
                "token": "activity-filled",
            },
        },
        "elements": detail_elements,
    }
