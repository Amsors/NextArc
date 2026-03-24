"""活动数据模型兼容层

本模块提供从 SecondClass 到数据库行的转换工具函数，
以及 SecondClassStatus 枚举（兼容 pyustc 的 Status）。
"""

import json
from datetime import datetime
from typing import Any, Optional

from pyustc.young import SecondClass, Status


class SecondClassStatus:
    """第二课堂活动状态（兼容 pyustc.Status 的静态包装）"""

    ABNORMAL = Status.ABNORMAL
    PUBLISHED = Status.PUBLISHED
    APPLYING = Status.APPLYING
    APPLY_ENDED = Status.APPLY_ENDED
    HOUR_PUBLIC = Status.HOUR_PUBLIC
    HOUR_APPEND_PUBLIC = Status.HOUR_APPEND_PUBLIC
    PUBLIC_ENDED = Status.PUBLIC_ENDED
    HOUR_APPLYING = Status.HOUR_APPLYING
    HOUR_APPROVED = Status.HOUR_APPROVED
    HOUR_REJECTED = Status.HOUR_REJECTED
    FINISHED = Status.FINISHED

    @staticmethod
    def is_status_code(code: int) -> bool:
        """检查是否为有效的状态码"""
        try:
            Status.from_code(code)
            return True
        except ValueError:
            return False

    @classmethod
    def from_code(cls, code: int) -> Optional[Status]:
        """根据状态码获取 Status 枚举成员"""
        try:
            return Status.from_code(code)
        except ValueError:
            return None


# ==================== SecondClass 扩展工具函数 ====================

def secondclass_from_db_row(row: dict[str, Any]) -> SecondClass:
    """
    从数据库行创建 SecondClass 对象
    
    注意：由于 SecondClass 使用 data 字典存储原始数据，
    我们需要将数据库中的 JSON 字符串还原为原始格式
    
    Args:
        row: 数据库行字典
        
    Returns:
        SecondClass 对象
    """
    # 构建原始 data 字典（与 API 响应格式一致）
    data = {
        "id": row["id"],
        "itemName": row["name"],
        "itemStatus": row["status"],
        "tel": row["tel"],
        "booleanRegistration": row["applied"],
        "needSignInfo": "1" if row["need_sign_info"] else "0",
        "conceive": row["conceive"],
        "itemCategory": "1" if row["is_series"] else "0",
    }

    # 处理时间字段（从 JSON 还原）
    if row.get("create_time"):
        try:
            create_data = json.loads(row["create_time"])
            if create_data and "datetime" in create_data:
                dt = datetime.strptime(create_data["datetime"], "%Y-%m-%d %H:%M:%S")
                data["createTime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    if row.get("apply_time"):
        try:
            apply_data = json.loads(row["apply_time"])
            if apply_data:
                if "start" in apply_data:
                    data["applySt"] = apply_data["start"]
                if "end" in apply_data:
                    data["applyEt"] = apply_data["end"]
        except (json.JSONDecodeError, KeyError):
            pass

    if row.get("hold_time"):
        try:
            hold_data = json.loads(row["hold_time"])
            if hold_data:
                if "start" in hold_data:
                    data["st"] = hold_data["start"]
                if "end" in hold_data:
                    data["et"] = hold_data["end"]
        except (json.JSONDecodeError, KeyError):
            pass

    # 处理可选字段
    if row.get("valid_hour") is not None:
        data["validHour"] = row["valid_hour"]

    if row.get("apply_num") is not None:
        data["applyNum"] = row["apply_num"]

    if row.get("apply_limit") is not None:
        data["peopleNum"] = row["apply_limit"]

    # 处理 module（从 JSON 还原）
    if row.get("module") and row["module"] != "null":
        try:
            module_data = json.loads(row["module"])
            if module_data:
                data["module"] = module_data.get("value")
                data["moduleName"] = module_data.get("text")
        except (json.JSONDecodeError, TypeError):
            pass

    # 处理 department（从 JSON 还原）
    if row.get("department") and row["department"] != "null":
        try:
            dept_data = json.loads(row["department"])
            if dept_data:
                data["businessDeptId"] = dept_data.get("id")
                data["bussinessDeptName"] = dept_data.get("name")
        except (json.JSONDecodeError, TypeError):
            pass

    # 处理 labels（从 JSON 还原）
    if row.get("labels") and row["labels"] != "null":
        try:
            labels_data = json.loads(row["labels"])
            if labels_data and isinstance(labels_data, list):
                data["itemLable"] = ",".join(str(l.get("id", "")) for l in labels_data)
                data["lableNames"] = ",".join(str(l.get("name", "")) for l in labels_data)
        except (json.JSONDecodeError, TypeError):
            pass

    # 处理 children_id 和 parent_id
    if row.get("children_id"):
        try:
            children_data = json.loads(row["children_id"])
            if children_data and isinstance(children_data, list):
                data["childrenIds"] = children_data
        except (json.JSONDecodeError, TypeError):
            pass

    if row.get("parent_id"):
        data["parentId"] = row["parent_id"]

    return SecondClass.from_dict(data)


def get_display_time(sc: SecondClass, field: str) -> str:
    """获取格式化的时间显示
    
    Args:
        sc: SecondClass 对象
        field: 字段名 ('create_time', 'apply_time', 'hold_time')
        
    Returns:
        格式化后的时间字符串
    """
    if field == "create_time":
        ct = sc.create_time
        if ct is None:
            return "没有从二课平台获取到数据！"
        return ct.strftime("%m-%d(%a) %H:%M")

    elif field == "apply_time":
        at = sc.apply_time
        if at is None:
            return "没有从二课平台获取到数据！"
        return f"{at.start.strftime('%m-%d(%a) %H:%M')} ~ {at.end.strftime('%m-%d(%a) %H:%M')}"

    elif field == "hold_time":
        ht = sc.hold_time
        if ht is None:
            return "没有从二课平台获取到数据！"
        return f"{ht.start.strftime('%m-%d(%a) %H:%M')} ~ {ht.end.strftime('%m-%d(%a) %H:%M')}"

    return "出现错误！"


def get_status_text(sc: SecondClass) -> str:
    """获取状态文本"""
    try:
        return sc.status.text
    except (AttributeError, ValueError):
        return f"未知状态({sc.data.get('itemStatus', 'unknown')})"


def get_apply_progress(sc: SecondClass) -> str:
    """获取报名进度"""
    if sc.apply_num is None:
        return "未知"
    limit = sc.apply_limit if sc.apply_limit else "∞"
    return f"{sc.apply_num}/{limit}"


def get_module_name(sc: SecondClass) -> str:
    """获取模块名称"""
    module = sc.module
    if module is None:
        return "未知"
    return module.text


def get_department_name(sc: SecondClass) -> str:
    """获取组织单位名称"""
    dept = sc.department
    if dept is None:
        return "未知"
    return dept.name


def get_labels_text(sc: SecondClass) -> str:
    """获取标签文本"""
    labels = sc.labels
    if not labels:
        return "无"
    return ", ".join(label.name for label in labels)


def get_description_text(sc: SecondClass) -> str:
    """获取活动描述文本"""
    if sc.conceive:
        return sc.conceive
    return sc.conceive or "无"

def format_secondclass_for_list(sc: SecondClass, index: int) -> str:
    """格式化为列表显示
    
    Args:
        sc: SecondClass 对象
        index: 序号（从1开始）
        
    Returns:
        格式化的文本
    """
    ret: str = (
        f"[{index}] {sc.name}({'系列活动' if sc.is_series else '单次活动'})\n"
        f"    📅 举办：{get_display_time(sc, 'hold_time')}\n"
        f"    📝 报名：{get_display_time(sc, 'apply_time')}\n"
        f"    📌 模块：{get_module_name(sc)}\n"
        f"    👥 组织单位：{get_department_name(sc)}\n"
        f"    📌 状态：{get_status_text(sc)}\n"
    )
    if not sc.is_series:
        ret += f"    ⏱️ 学时：{sc.valid_hour or '未知'}\n"
        ret += f"    👥 报名：{get_apply_progress(sc)}\n"

    return ret


def secondclass_to_display_dict(sc: SecondClass) -> dict[str, str]:
    """转换为显示用的字典
    
    Args:
        sc: SecondClass 对象
        
    Returns:
        显示用的字典
    """
    return {
        "id": sc.id,
        "name": sc.name,
        "status": get_status_text(sc),
        "hold_time": get_display_time(sc, "hold_time"),
        "apply_time": get_display_time(sc, "apply_time"),
        "valid_hour": str(sc.valid_hour) if sc.valid_hour else "未知",
        "apply_progress": get_apply_progress(sc),
        "module": get_module_name(sc),
        "department": get_department_name(sc),
        "labels": get_labels_text(sc),
    }
