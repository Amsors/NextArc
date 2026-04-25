"""消息格式化工具"""

from datetime import datetime
from typing import Optional

from pyustc.young import SecondClass

from src.core import FilteredActivity
from src.models.secondclass_view import (
    format_secondclass_for_list,
)


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

    notification_errors = result.get("notification_errors") or []
    if notification_errors:
        lines.append("")
        lines.append("通知错误：")
        for error in notification_errors:
            lines.append(f"  {error}")

    return "\n".join(lines)


def format_error_message(error: str, context: str = "") -> str:
    """格式化错误消息"""
    lines = ["操作失败"]

    if context:
        lines.append(f"上下文：{context}")

    lines.append(f"错误：{error}")

    return "\n".join(lines)
