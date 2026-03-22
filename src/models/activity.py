"""活动数据模型"""

import json
import time
from typing import Any, Optional, Self, TYPE_CHECKING

from pydantic import BaseModel
from enum import Enum

from pyustc.young import TimePeriod

if TYPE_CHECKING:
    from pyustc.young.second_class import SecondClass

class SecondClassStatus(Enum):
    ABNORMAL = -3, "异常结项"
    PUBLISHED = 10, "发布"
    APPLYING = 26, "报名中"
    APPLY_ENDED = 28, "报名已结束"
    HOUR_PUBLIC = 30, "学时公示中"
    HOUR_APPEND_PUBLIC = 31, "追加学时公示"
    PUBLIC_ENDED = 32, "公示已结束"
    HOUR_APPLYING = 33, "学时申请中"
    HOUR_APPROVED = 34, "学时审核通过"
    HOUR_REJECTED = 35, "学时驳回"
    FINISHED = 40, "结项"

    @staticmethod
    def is_status_code(code: int) -> bool:
        return any(member.value[0] == code for member in SecondClassStatus)

    @classmethod
    def from_code(cls, code: int) -> "SecondClassStatus | None":
        """根据状态码获取枚举成员"""
        try:
            for member in cls:
                if member.value[0] == code:
                    return member
        except (ValueError, TypeError):
            pass
        return None


class Activity(BaseModel):
    """
    第二课堂活动模型
    与 SecondClassDB 的表结构保持一致
    """
    id: str
    name: str
    status: int
    create_time: Optional[str] = None  # JSON字符串
    apply_time: Optional[str] = None   # JSON字符串
    hold_time: Optional[str] = None    # JSON字符串
    tel: str
    valid_hour: Optional[float] = None
    apply_num: Optional[int] = None
    apply_limit: Optional[int] = None  # 可能为 null
    applied: int
    need_sign_info: int
    module: Optional[str] = None       # JSON字符串
    department: Optional[str] = None   # JSON字符串
    labels: Optional[str] = None       # JSON字符串
    conceive: str
    is_series: int
    children_id: Optional[str] = None  # JSON字符串
    parent_id: Optional[str] = None
    scan_timestamp: int
    
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Self:
        """从数据库行字典创建实例"""
        return cls(**dict(row))
    
    def get_display_time(self, field: str) -> str:
        """获取格式化的时间显示"""
        time_json = getattr(self, field)
        if not time_json:
            return "待定"
        try:
            data = json.loads(time_json)
            if field == "create_time":
                return data.get("datetime", "未知")
            else:  # apply_time, hold_time
                start = data.get("start", "未知")
                end = data.get("end", "未知")
                return f"{start} ~ {end}"
        except (json.JSONDecodeError, TypeError):
            return "解析错误"
    
    def get_status_text(self) -> str:
        """获取状态文本"""
        # 使用 from_code 获取状态，避免直接构造枚举
        status_obj = SecondClassStatus.from_code(self.status)
        if status_obj:
            return status_obj.value[1]
        return f"未知状态({self.status})"
    
    def get_apply_progress(self) -> str:
        """获取报名进度"""
        if self.apply_num is None:
            return "未知"
        limit = self.apply_limit if self.apply_limit is not None else "∞"
        return f"{self.apply_num}/{limit}"
    
    def get_module_name(self) -> str:
        """获取模块名称"""
        if not self.module:
            return "未知"
        if self.module=="null":
            return "未知"
        try:
            data = json.loads(self.module)
            if not data:
                return "未知"
            return data.get("text", "未知")
        except (json.JSONDecodeError, TypeError):
            return "解析错误"
    
    def get_department_name(self) -> str:
        """获取组织单位名称"""
        if not self.department:
            return "未知"
        if self.department=="null":
            return "未知"
        try:
            data = json.loads(self.department)
            return data.get("name", "未知")
        except (json.JSONDecodeError, TypeError):
            return "解析错误"
    
    def get_labels_text(self) -> str:
        """获取标签文本"""
        if not self.labels:
            return "无"
        if self.labels=="null":
            return "无"
        try:
            data = json.loads(self.labels)
            if not data:
                return "无"
            if not isinstance(data, list):
                return ", ".join(item.get("name", "") for item in data)
            return str(data)
        except (json.JSONDecodeError, TypeError):
            return "解析错误"
    
    def to_display_dict(self) -> dict[str, str]:
        """转换为显示用的字典"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.get_status_text(),
            "hold_time": self.get_display_time("hold_time"),
            "apply_time": self.get_display_time("apply_time"),
            "valid_hour": str(self.valid_hour) if self.valid_hour else "未知",
            "apply_progress": self.get_apply_progress(),
            "module": self.get_module_name(),
            "department": self.get_department_name(),
            "labels": self.get_labels_text(),
        }
    
    def format_for_list(self, index: int) -> str:
        """格式化为列表显示"""
        return (
            f"[{index}] {self.name}\n"
            f"    📅 举办：{self.get_display_time('hold_time')}\n"
            f"    📝 报名：{self.get_display_time('apply_time')}\n"
            f"    ⏱️ 学时：{self.valid_hour or '未知'}\n"
            f"    📌 模块：{self.get_module_name()}\n"
            f"    👥 组织单位：{self.get_department_name()}\n"
            f"    👥 报名：{self.get_apply_progress()}\n"
            f"    📌 状态：{self.get_status_text()}"
        )
