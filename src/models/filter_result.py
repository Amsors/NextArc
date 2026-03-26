"""筛选结果模型

提供统一的筛选结果数据模型，用于表示被筛选掉的活动。
"""

from dataclasses import dataclass
from typing import Optional, Any

from pyustc.young import SecondClass


@dataclass
class FilteredActivity:
    """被筛选掉的活动信息

    用于统一表示各种筛选器（AI筛选、时间筛选、忽略数据库筛选）
    过滤掉的活动及其原因。

    Attributes:
        activity: 被过滤的活动对象（SecondClass）
        reason: 过滤原因的描述文本
        filter_type: 筛选器类型标识（如 'ai', 'time', 'ignore' 等）
        extra_data: 可选的额外数据，用于存储特定筛选器的详细信息
                   例如时间筛选可以存储冲突的时间段信息
    """
    activity: SecondClass
    reason: str
    filter_type: str = "unknown"
    extra_data: Optional[dict[str, Any]] = None

    def __post_init__(self):
        """初始化后的处理，确保 filter_type 是有效的字符串"""
        if not self.filter_type or self.filter_type == "unknown":
            # 尝试从 reason 推断 filter_type
            if self.reason:
                reason_lower = self.reason.lower()
                if "ai" in reason_lower or "人工智能" in reason or "模型" in reason:
                    self.filter_type = "ai"
                elif "时间" in reason or "冲突" in reason:
                    self.filter_type = "time"
                elif "忽略" in reason or "不感兴趣" in reason or "数据库" in reason:
                    self.filter_type = "ignore"

    @property
    def activity_id(self) -> str:
        """获取活动ID"""
        return self.activity.id

    @property
    def activity_name(self) -> str:
        """获取活动名称"""
        return self.activity.name

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式

        Returns:
            包含过滤信息的字典
        """
        return {
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "reason": self.reason,
            "filter_type": self.filter_type,
            "extra_data": self.extra_data,
        }

    def __str__(self) -> str:
        """字符串表示"""
        return (f"FilteredActivity(id={self.activity_id}, "
                f"name={self.activity_name}, "
                f"reason={self.reason}, "
                f"type={self.filter_type})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


@dataclass
class FilterResult:
    """筛选结果容器

    包含保留的活动和被过滤的活动列表。

    Attributes:
        kept: 通过筛选保留的活动列表
        filtered: 被过滤掉的活动列表（FilteredActivity 对象）
    """
    kept: list[SecondClass]
    filtered: list[FilteredActivity]

    def __len__(self) -> int:
        """返回总活动数（保留 + 过滤）"""
        return len(self.kept) + len(self.filtered)

    @property
    def total_count(self) -> int:
        """获取总活动数"""
        return len(self)

    @property
    def kept_count(self) -> int:
        """获取保留的活动数"""
        return len(self.kept)

    @property
    def filtered_count(self) -> int:
        """获取被过滤的活动数"""
        return len(self.filtered)

    def get_filtered_by_type(self, filter_type: str) -> list[FilteredActivity]:
        """获取特定类型的被过滤活动

        Args:
            filter_type: 筛选器类型（如 'ai', 'time', 'ignore'）

        Returns:
            该类型的被过滤活动列表
        """
        return [f for f in self.filtered if f.filter_type == filter_type]

    def to_summary(self) -> dict[str, Any]:
        """生成筛选结果的摘要信息

        Returns:
            包含统计信息的字典
        """
        return {
            "total": self.total_count,
            "kept": self.kept_count,
            "filtered": self.filtered_count,
            "by_type": {
                "ai": len(self.get_filtered_by_type("ai")),
                "time": len(self.get_filtered_by_type("time")),
                "ignore": len(self.get_filtered_by_type("ignore")),
            }
        }
