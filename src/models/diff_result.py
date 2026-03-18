"""差异结果数据模型"""

from typing import Any, Literal

from pydantic import BaseModel


class FieldChange(BaseModel):
    """单个字段的变化"""
    field_name: str
    old_value: Any
    new_value: Any
    
    def format(self) -> str:
        """格式化为可读文本"""
        old = self.old_value if self.old_value is not None else "空"
        new = self.new_value if self.new_value is not None else "空"
        return f"    {self.field_name}: {old} → {new}"


class ActivityChange(BaseModel):
    """单个活动的变化"""
    activity_id: str
    activity_name: str
    change_type: Literal["added", "removed", "modified"]
    field_changes: list[FieldChange] = []
    
    def get_type_emoji(self) -> str:
        """获取变化类型的 emoji"""
        return {
            "added": "🆕",
            "removed": "❌",
            "modified": "📝",
        }.get(self.change_type, "❓")
    
    def get_type_text(self) -> str:
        """获取变化类型的中文文本"""
        return {
            "added": "新增",
            "removed": "删除",
            "modified": "修改",
        }.get(self.change_type, "未知")
    
    def format(self, index: int) -> str:
        """格式化为可读文本"""
        lines = [f"[{index}] {self.activity_name}"]
        if self.change_type == "modified" and self.field_changes:
            for fc in self.field_changes:
                lines.append(fc.format())
        return "\n".join(lines)


class DiffResult(BaseModel):
    """差异对比结果"""
    added: list[ActivityChange] = []
    removed: list[ActivityChange] = []
    modified: list[ActivityChange] = []
    
    def has_changes(self) -> bool:
        """是否有变化"""
        return bool(self.added or self.removed or self.modified)
    
    def get_summary(self) -> str:
        """获取差异摘要"""
        return f"新增 {len(self.added)} 个，删除 {len(self.removed)} 个，修改 {len(self.modified)} 个"
    
    def format_full(self) -> str:
        """格式化为完整报告"""
        lines = ["📊 数据库对比结果：", ""]
        
        if not self.has_changes():
            lines.append("✅ 无变化")
            return "\n".join(lines)
        
        # 新增
        if self.added:
            lines.append(f"🆕 新增活动（{len(self.added)}个）：")
            for i, change in enumerate(self.added, 1):
                lines.append(change.format(i))
            lines.append("")
        
        # 删除
        if self.removed:
            lines.append(f"❌ 删除活动（{len(self.removed)}个）：")
            for i, change in enumerate(self.removed, 1):
                lines.append(change.format(i))
            lines.append("")
        
        # 修改
        if self.modified:
            lines.append(f"📝 信息修改（{len(self.modified)}个）：")
            for i, change in enumerate(self.modified, 1):
                lines.append(change.format(i))
            lines.append("")
        
        return "\n".join(lines)
    
    def get_enrolled_changes(self, enrolled_ids: set[str]) -> list[ActivityChange]:
        """获取已报名活动的变化"""
        changes = []
        for change in self.modified:
            if change.activity_id in enrolled_ids:
                changes.append(change)
        return changes
