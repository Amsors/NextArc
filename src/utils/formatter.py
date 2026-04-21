"""消息格式化工具"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pyustc.young import SecondClass, ParticipationForm

from src.core import FilteredActivity
from src.models import DiffResult
from src.utils.logger import get_logger
from src.models.activity import (
    format_secondclass_for_list,
    get_display_time,
    get_status_text,
    get_apply_progress,
    get_module_name,
    get_department_name,
    get_labels_text, get_conceive_text, get_place_info, get_participation_form, get_description_text
)

logger = get_logger("utils.formatter")


@dataclass
class CardButtonConfig:
    """卡片按钮配置类"""
    show_ignore_button: bool = True
    show_interested_button: bool = True
    show_join_button: bool = True
    show_cancel_button: bool = False
    show_children_button: bool = True
    is_ignored: bool = False

    def get_buttons(self, act: SecondClass) -> list[dict]:
        """根据配置生成按钮列表"""
        buttons = []

        if self.show_interested_button:
            buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "感兴趣"},
                "type": "default",
                "value": {
                    "action": "toggle_interested",
                    "activity_id": act.id,
                    "activity_name": act.name
                }
            })

        if self.show_ignore_button:
            ignore_button_text = "已忽略" if self.is_ignored else "不感兴趣"
            ignore_button_type = "default" if self.is_ignored else "danger"
            buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": ignore_button_text},
                "type": ignore_button_type,
                "value": {
                    "action": "toggle_ignore",
                    "activity_id": act.id,
                    "activity_name": act.name
                }
            })

        if self.show_cancel_button:
            buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "取消报名"},
                "type": "danger",
                "value": {
                    "action": "cancel",
                    "activity_id": act.id,
                    "activity_name": act.name
                }
            })

        if act.is_series:
            if self.show_children_button:
                buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看子活动"},
                    "type": "primary",
                    "value": {
                        "action": "view_children",
                        "activity_id": act.id,
                        "activity_name": act.name
                    }
                })
        else:
            if self.show_join_button:
                buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "去报名"},
                    "type": "primary",
                    "value": {
                        "action": "join",
                        "activity_id": act.id,
                        "activity_name": act.name
                    }
                })

        return buttons


def format_activity_list(activities: list[SecondClass], title: str = "活动列表", simple_format: bool = False) -> str:
    """格式化活动列表为文本"""
    if not activities:
        return f"{title}\n\n暂无活动"

    lines = [f"{title}（共{len(activities)}条）："]

    for i, act in enumerate(activities, 1):
        lines.append(format_secondclass_for_list(act, i, simple_format))
        if not simple_format:
            lines.append("")

    return "\n".join(lines)


def format_ai_filtered_result(
        activities_filtered: list[FilteredActivity],
        include_reasons: bool = False,
) -> str:
    """格式化AI筛选掉的活动列表"""
    if not activities_filtered:
        return ""

    lines = ["因AI筛选被筛选掉的活动（共{}条）：".format(len(activities_filtered))]

    for i, filtered in enumerate(activities_filtered, 1):
        lines.append(format_secondclass_for_list(filtered.activity, i, simple_format=True))
        if include_reasons:
            lines.append(f"   原因：{filtered.reason}")

    lines.append("")
    return "\n".join(lines)


def format_time_filtered_result(activities_filtered: list[FilteredActivity]) -> str:
    """格式化因时间冲突被筛选掉的活动列表"""
    activities = [act.activity for act in activities_filtered]
    lines = format_activity_list(activities, "因空闲时间不符被筛选掉的活动", simple_format=True)
    lines += "\n"
    return lines


def format_db_filtered_result(activities_filtered: list[FilteredActivity]) -> str:
    """格式化因数据库记录被筛选掉的活动列表"""
    activities = [act.activity for act in activities_filtered]
    lines = format_activity_list(activities, "因数据库记录不感兴趣被筛选掉的活动", simple_format=True)
    lines += "\n"
    return lines


def format_enrolled_filtered_result(activities_filtered: list[FilteredActivity]) -> str:
    """格式化因已报名被筛选掉的活动列表"""
    activities = [act.activity for act in activities_filtered]
    lines = format_activity_list(activities, "因已报名被筛选掉的活动", simple_format=True)
    lines += "\n"
    return lines


def format_overlay_filtered_result(activities_filtered: list[FilteredActivity]) -> str:
    """格式化因与已报名活动时间重叠被筛选掉的活动列表"""
    activities = [act.activity for act in activities_filtered]
    lines = format_activity_list(activities, "因与已报名活动时间重叠被筛选掉的活动", simple_format=True)
    lines += "\n"
    return lines


def format_status_message(
        is_running: bool,
        last_scan: Optional[datetime],
        next_scan: Optional[datetime],
        is_logged_in: bool,
        db_count: int,
        ignore_count: int = 0,
        interested_count: int = 0,
) -> str:
    """格式化状态消息"""
    lines = []

    if is_running:
        lines.append("服务运行中")
    else:
        lines.append("服务已停止")


    lines.append("")

    if last_scan:
        lines.append(f"最后扫描：{last_scan.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        lines.append("最后扫描：无")

    if next_scan:
        lines.append(f"下次扫描：{next_scan.strftime('%Y-%m-%d %H:%M:%S')}")

    lines.append("")

    lines.append(f"数据库数量：{db_count}")
    lines.append(f"不感兴趣活动：{ignore_count}")
    lines.append(f"⭐ 感兴趣活动：{interested_count}")

    return "\n".join(lines)


def format_scan_result(result: dict) -> str:
    """格式化扫描结果"""
    if not result.get("success"):
        error = result.get("error", "未知错误")
        return f"扫描失败：{error}"

    lines = ["扫描完成", ""]

    if result.get("new_db_path"):
        lines.append(f"数据库：{result['new_db_path'].name}")

    lines.append(f"活动数量：{result.get('activity_count', 0)}")

    if result.get("diff"):
        diff = result["diff"]
        lines.append(f"差异：{diff.get_summary()}")

    return "\n".join(lines)


def format_error_message(error: str, context: str = "") -> str:
    """格式化错误消息"""
    lines = ["操作失败"]

    if context:
        lines.append(f"上下文：{context}")

    lines.append(f"错误：{error}")

    return "\n".join(lines)


def format_help_message() -> str:
    """格式化帮助消息"""
    return """NextArc - 第二课堂活动监控机器人

可用指令：
/update - 手动更新数据库
/check  - 更新并显示与上次扫描的差异
/valid [重新扫描] [全部] - 显示可报名的活动
/info   - 显示已报名的所有活动
/cancel 序号 - 取消指定序号的报名
/search 关键词 - 搜索活动
/join 序号 - 报名搜索结果的指定活动
/alive  - 检查服务状态

提示：
- 搜索结果是有效期5分钟
- 报名/取消报名需要二次确认
- /valid 默认启用 AI/时间筛选，加「全部」参数可查看所有活动
"""


def build_activity_card(
        activities: list[SecondClass],
        title: str = "活动列表",
        ignored_ids: set[str] | None = None,
        start_index: int = 1,
        button_config: CardButtonConfig | None = None,  # None表示使用默认配置（显示忽略和报名按钮）
        ai_reasons: dict[str, str] | None = None,
        overlap_reasons: dict[str, str] | None = None,
) -> dict:
    """构建活动列表的消息卡片（使用折叠面板）"""
    if ignored_ids is None:
        ignored_ids = set()

    if ai_reasons is None:
        ai_reasons = {}

    if overlap_reasons is None:
        overlap_reasons = {}

    logger.debug(f"build_activity_card: activities={len(activities)}, ai_reasons_keys={list(ai_reasons.keys())}, overlap_reasons_keys={list(overlap_reasons.keys())}")

    if not activities:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{title}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": "暂无活动"}
                }
            ]
        }

    elements = []

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"共找到 **{len(activities)}** 个活动"
        }
    })

    elements.append({"tag": "hr"})

    for i, act in enumerate(activities, start_index):
        is_ignored = act.id in ignored_ids
        if button_config is None:
            act_button_config = CardButtonConfig()
        else:
            from dataclasses import replace
            act_button_config = replace(button_config, is_ignored=is_ignored)
        ai_reason = ai_reasons.get(act.id)
        overlap_reason = overlap_reasons.get(act.id)
        collapsible_panel = _build_activity_collapsible_panel(
            act, i, act_button_config, ai_reason=ai_reason, overlap_reason=overlap_reason
        )
        elements.append(collapsible_panel)

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{title}"},
            "template": "blue"
        },
        "elements": elements
    }


def _build_activity_collapsible_panel(
        act: SecondClass,
        index: int,
        button_config: CardButtonConfig | None = None,
        ai_reason: str | None = None,
        overlap_reason: str | None = None,
) -> dict:
    """为单个活动构建折叠面板"""
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


    detail_elements = []
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**举办**\n{get_display_time(act, 'hold_time')}"
        }
    )
    if not act.is_series:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**报名**\n{get_display_time(act, 'apply_time')}"
            }
        )
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**模块**: {get_module_name(act)}"
        }
    )
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**组织单位**: {get_department_name(act)}"
        }
    )
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**地点**: {get_place_info(act)}"
        }
    )
    if get_participation_form(act):
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**参与形式**: {get_participation_form(act)}"
            }
        )

    if act.is_series:
        detail_elements.append({
            "tag": "markdown",
            "content": f"**状态：** {get_status_text(act)}"
        })
    else:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**状态**: {get_status_text(act)}"
            }
        )
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**学时**: {act.valid_hour or '未知'}"
            }
        )
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**报名**: {get_apply_progress(act)}"
            }
        )

    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**✏️ 活动构想**\n{get_conceive_text(act)}"
        }
    )

    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**📚️ 活动描述**\n{get_description_text(act)}"
        }
    )

    labels = get_labels_text(act)
    if labels and labels != "无":
        detail_elements.append({
            "tag": "markdown",
            "content": f"**标签：** {labels}"
        })

    if overlap_reason:
        detail_elements.append({
            "tag": "markdown",
            "content": f"**⚠️ 时间重叠**\n{overlap_reason}"
        })

    if ai_reason:
        detail_elements.append({
            "tag": "markdown",
            "content": f"**🤖 AI 判断理由**\n{ai_reason}"
        })

    detail_elements.append({"tag": "hr"})

    button_elements = button_config.get_buttons(act)
    if button_elements:
        detail_elements.append({
            "tag": "action",
            "actions": button_elements
        })

    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "background_color": "grey",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": header_title
            },
            "icon": {
                "tag": "standard_icon",
                "token": "activity-filled"
            }
        },
        "elements": detail_elements
    }
