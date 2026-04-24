"""SecondClass 兼容层。

阶段 8 后，数据库行转换由 ``secondclass_mapper`` 负责，展示字段读取由
``secondclass_view`` 负责。本模块保留旧导入路径，避免一次性迁移所有调用方。
"""

from typing import Optional

from pyustc.young import Status

from .secondclass_mapper import secondclass_from_db_row, secondclass_to_db_row
from .secondclass_view import (
    format_secondclass_for_list,
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
    secondclass_to_display_dict,
)


class SecondClassStatus:
    """第二课堂活动状态（兼容 pyustc.Status）"""

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
        try:
            Status.from_code(code)
            return True
        except ValueError:
            return False

    @classmethod
    def from_code(cls, code: int) -> Optional[Status]:
        try:
            return Status.from_code(code)
        except ValueError:
            return None


__all__ = [
    "SecondClassStatus",
    "secondclass_from_db_row",
    "secondclass_to_db_row",
    "get_display_time",
    "get_status_text",
    "get_apply_progress",
    "get_module_name",
    "get_department_name",
    "get_labels_text",
    "get_conceive_text",
    "get_description_text",
    "get_place_info",
    "get_participation_form",
    "format_secondclass_for_list",
    "secondclass_to_display_dict",
]
