"""消息格式化工具"""

from datetime import datetime
from typing import Optional

from pyustc.young import SecondClass

from src.core import FilteredActivity
from src.models import DiffResult
from src.models.activity import (
    format_secondclass_for_list,
    get_display_time,
    get_status_text,
    get_apply_progress,
    get_module_name,
    get_department_name,
    get_labels_text, get_description_text,
)


def format_activity_list(activities: list[SecondClass], title: str = "活动列表", simple_format: bool = False) -> str:
    """
    格式化活动列表
    
    Args:
        activities: 活动列表
        title: 列表标题
        simple_format: 是否使用简单格式

    Returns:
        格式化后的文本    """
    if not activities:
        return f"📋 {title}\n\n暂无活动"

    lines = [f"📋 {title}（共{len(activities)}条）："]

    for i, act in enumerate(activities, 1):
        lines.append(format_secondclass_for_list(act, i, simple_format))
        if not simple_format:
            lines.append("")

    return "\n".join(lines)


def format_diff_result(diff: DiffResult) -> str:
    """
    格式化差异结果
    
    Args:
        diff: 差异结果
        
    Returns:
        格式化后的文本
    """
    return diff.format_full()


def format_enrolled_list(activities: list[SecondClass]) -> str:
    """
    格式化已报名活动列表
    
    Args:
        activities: 已报名活动列表
        
    Returns:
        格式化后的文本
    """
    lines = format_activity_list(activities, "已报名活动")

    if activities:
        lines += "\n💡 使用 /cancel 序号 取消报名\n"

    return lines


def format_search_results(activities: list[SecondClass], keyword: str, hint: str = "") -> str:
    """
    格式化搜索结果
    
    Args:
        activities: 搜索结果列表
        keyword: 搜索关键词
        hint: 提示信息

    Returns:
        格式化后的文本
    """
    lines = format_activity_list(activities, f'搜索「{keyword}」结果')

    if activities:
        lines += "\n💡 使用 /join 序号 报名指定活动\n"
        lines += "⚠️ 搜索结果有效期5分钟\n"
    else:
        lines += "未找到匹配的活动，请尝试其他关键词\n"

    if hint:
        lines += f"\n{hint}"

    return lines


def format_ai_filtered_result(activities: list[SecondClass]) -> str:
    lines = format_activity_list(activities, "被AI筛选掉的活动", simple_format=True)
    return lines


def format_time_filtered_result(activities_filtered: list[FilteredActivity]) -> str:
    activities = [act.activity for act in activities_filtered]
    lines = format_activity_list(activities, "因空闲时间不符被筛选掉的活动", simple_format=True)
    return lines


def format_db_filtered_result(activities: list[SecondClass]) -> str:
    lines = format_activity_list(activities, "因加入不感兴趣数据库被筛选掉的活动", simple_format=True)
    return lines


def format_status_message(
        is_running: bool,
        last_scan: Optional[datetime],
        next_scan: Optional[datetime],
        is_logged_in: bool,
        db_count: int,
        ignore_count: int = 0,
) -> str:
    """
    格式化状态消息
    
    Args:
        is_running: 是否运行中
        last_scan: 上次扫描时间
        next_scan: 下次扫描时间
        is_logged_in: 是否已登录
        db_count: 数据库数量
        ignore_count: 被忽略的活动数量
        
    Returns:
        格式化后的文本
    """
    lines = ["📊 服务状态", ""]

    # 运行状态
    if is_running:
        lines.append("🟢 服务运行中")
    else:
        lines.append("🔴 服务已停止")

    # 登录状态
    if is_logged_in:
        lines.append("✅ 已登录")
    else:
        lines.append("❌ 未登录")

    lines.append("")

    # 扫描信息
    if last_scan:
        lines.append(f"🕐 最后扫描：{last_scan.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        lines.append("🕐 最后扫描：无")

    if next_scan:
        lines.append(f"⏰ 下次扫描：{next_scan.strftime('%Y-%m-%d %H:%M:%S')}")

    lines.append(f"🗄️  数据库数量：{db_count}")
    lines.append(f"🗑️  不感兴趣活动：{ignore_count}")

    return "\n".join(lines)


def format_scan_result(result: dict) -> str:
    """
    格式化扫描结果
    
    Args:
        result: scan() 方法返回的结果字典
        
    Returns:
        格式化后的文本
    """
    if not result.get("success"):
        error = result.get("error", "未知错误")
        return f"❌ 扫描失败：{error}"

    lines = ["✅ 扫描完成", ""]

    if result.get("new_db_path"):
        lines.append(f"🗄️  数据库：{result['new_db_path'].name}")

    lines.append(f"📊 活动数量：{result.get('activity_count', 0)}")

    if result.get("diff"):
        diff = result["diff"]
        lines.append(f"📝 差异：{diff.get_summary()}")

    return "\n".join(lines)


def format_error_message(error: str, context: str = "") -> str:
    """
    格式化错误消息
    
    Args:
        error: 错误信息
        context: 错误上下文
        
    Returns:
        格式化后的文本
    """
    lines = ["❌ 操作失败"]

    if context:
        lines.append(f"上下文：{context}")

    lines.append(f"错误：{error}")

    return "\n".join(lines)


def format_help_message() -> str:
    """
    格式化帮助消息
    
    Returns:
        格式化后的文本
    """
    return """🤖 NextArc - 第二课堂活动监控机器人

可用指令：
/update - 手动更新数据库
/check  - 更新并显示与上次扫描的差异
/valid [重新扫描] [全部] - 显示可报名的活动
/info   - 显示已报名的所有活动
/cancel 序号 - 取消指定序号的报名
/search 关键词 - 搜索活动
/join 序号 - 报名搜索结果的指定活动
/alive  - 检查服务状态

💡 提示：
- 搜索结果是有效期5分钟
- 报名/取消报名需要二次确认
- /valid 默认启用 AI/时间筛选，加「全部」参数可查看所有活动
"""


def build_activity_card(activities: list[SecondClass], title: str = "活动列表") -> dict:
    """
    构建活动列表的消息卡片（使用折叠面板）
    
    Args:
        activities: 活动列表
        title: 卡片标题
        
    Returns:
        飞书消息卡片 JSON 字典
    """
    if not activities:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📋 {title}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": "暂无活动"}
                }
            ]
        }

    # 构建折叠面板元素列表
    elements = []

    # 添加统计信息
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"共找到 **{len(activities)}** 个活动"
        }
    })

    # 添加分隔线
    elements.append({"tag": "hr"})

    # 为每个活动创建一个折叠面板
    for i, act in enumerate(activities, 1):
        collapsible_panel = _build_activity_collapsible_panel(act, i)
        elements.append(collapsible_panel)

    # # 添加底部提示
    # elements.append({"tag": "hr"})
    # elements.append({
    #     "tag": "note",
    #     "elements": [
    #         {
    #             "tag": "plain_text",
    #             "content": "💡 点击活动名称可查看详情"
    #         }
    #     ]
    # })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📋 {title}"},
            "template": "blue"
        },
        "elements": elements
    }


def _build_activity_collapsible_panel(act: SecondClass, index: int) -> dict:
    """
    为单个活动构建折叠面板
    
    Args:
        act: SecondClass 活动对象
        index: 序号（从1开始）
        
    Returns:
        折叠面板 JSON 字典
    """
    activity_type = "系列活动" if act.is_series else "单次活动"

    # 面板标题：活动名称和类型
    header_title = f"[{index}] {act.name} ({activity_type})"

    # 构建详细内容元素
    detail_elements = []
    detail_elements.append(
        {

            "tag": "markdown",
            "content": f"**📅 举办**\n{get_display_time(act, 'hold_time')}"
        }
    )
    if not act.is_series:
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**📝 报名**\n{get_display_time(act, 'apply_time')}"
            }
        )
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**📌 模块**: {get_module_name(act)}"

        }
    )
    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**👥 组织单位**: {get_department_name(act)}"

        }
    )

    # 状态和学时/报名人数
    if act.is_series:
        # 系列活动只显示状态
        detail_elements.append({
            "tag": "markdown",
            "content": f"**📌 状态：** {get_status_text(act)}"
        })
    else:
        # 单次活动显示状态、学时和报名人数
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**📌 状态**: {get_status_text(act)}"
            }
        )
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**⏱️ 学时**: {act.valid_hour or '未知'}"
            }
        )
        detail_elements.append(
            {
                "tag": "markdown",
                "content": f"**👥 报名**: {get_apply_progress(act)}"
            }
        )

    detail_elements.append(
        {
            "tag": "markdown",
            "content": f"**👥 活动描述**\n{get_description_text(act)}"
        }
    )

    # 标签（如果有）
    labels = get_labels_text(act)
    if labels and labels != "无":
        detail_elements.append({
            "tag": "markdown",
            "content": f"**🏷️ 标签：** {labels}"
        })

    # 构建折叠面板
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
