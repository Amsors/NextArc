"""差异结果数据模型"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class FieldChange(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any

    def format(self) -> str:
        old = self.old_value if self.old_value is not None else "空"
        new = self.new_value if self.new_value is not None else "空"
        return f"    {self.field_name}: {old} → {new}"


class ActivityChange(BaseModel):
    activity_id: str
    activity_name: str
    change_type: Literal["added", "removed", "modified"]
    field_changes: list[FieldChange] = []

    def format(self, index: int) -> str:
        lines = [f"[{index}] {self.activity_name}"]
        if self.change_type == "modified" and self.field_changes:
            for fc in self.field_changes:
                lines.append(fc.format())
        return "\n".join(lines)


class DiffResult(BaseModel):
    added: list[ActivityChange] = []
    removed: list[ActivityChange] = []
    modified: list[ActivityChange] = []
    old_scan_time: Optional[datetime] = None
    new_scan_time: Optional[datetime] = None

    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    def get_summary(self) -> str:
        return f"新增 {len(self.added)} 个，删除 {len(self.removed)} 个，修改 {len(self.modified)} 个"

    def format_full(self) -> str:
        lines = ["数据库对比结果：", ""]

        if not self.has_changes():
            lines.append("无变化")
            return "\n".join(lines)

        if self.added:
            lines.append(f"新增活动（{len(self.added)}个）：")
            for i, change in enumerate(self.added, 1):
                lines.append(change.format(i))
            lines.append("")

        if self.removed:
            lines.append(f"删除活动（{len(self.removed)}个）：")
            for i, change in enumerate(self.removed, 1):
                lines.append(change.format(i))
            lines.append("")

        if self.modified:
            lines.append(f"信息修改（{len(self.modified)}个）：")
            for i, change in enumerate(self.modified, 1):
                lines.append(change.format(i))
            lines.append("")

        return "\n".join(lines)

    def get_enrolled_changes(self, enrolled_ids: set[str]) -> list[ActivityChange]:
        changes = []
        for change in self.modified:
            if change.activity_id in enrolled_ids:
                changes.append(change)
        return changes

    def format_new_activities_notification(self) -> str:
        if not self.added:
            return ""

        lines = ["发现新的第二课堂活动！", ""]

        if self.old_scan_time and self.new_scan_time:
            lines.append(f"数据对比：")
            lines.append(f"   上次采集：{self.old_scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"   本次采集：{self.new_scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")

        lines.append(f"新增活动（共{len(self.added)}个）：")
        lines.append("")

        for i, change in enumerate(self.added, 1):
            lines.append(f"[{i}] {change.activity_name}")

        lines.append("")
        lines.append("")

        return "\n".join(lines)
