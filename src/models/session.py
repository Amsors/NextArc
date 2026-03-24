"""用户会话数据模型"""

from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pyustc.young import SecondClass

from src.utils.logger import get_logger

logger = get_logger("session")


class SearchSession(BaseModel):
    """搜索会话上下文"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    keyword: str
    results: list[SecondClass]
    created_at: datetime

    def is_expired(self) -> bool:
        """是否已过期（5分钟）"""
        return datetime.now() - self.created_at > timedelta(minutes=5)

    def get_result_by_index(self, index: int) -> Optional[SecondClass]:
        """
        根据序号获取搜索结果
        
        Args:
            index: 序号（从1开始）
            
        Returns:
            SecondClass 或 None（序号无效或已过期）
        """
        if self.is_expired():
            return None
        if index < 1 or index > len(self.results):
            return None
        return self.results[index - 1]


class DisplayedActivitiesSession(BaseModel):
    """最近显示的活动列表会话（用于"不感兴趣"功能）"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    activities: list[SecondClass]
    source: str  # 来源："valid", "new_activities", "search" 等
    created_at: datetime

    def is_expired(self) -> bool:
        """是否已过期（10分钟）"""
        return datetime.now() - self.created_at > timedelta(minutes=10)

    def get_activity_by_index(self, index: int) -> Optional[SecondClass]:
        """
        根据序号获取活动
        
        Args:
            index: 序号（从1开始）
            
        Returns:
            SecondClass 或 None（序号无效或已过期）
        """
        if self.is_expired():
            return None
        if index < 1 or index > len(self.activities):
            return None
        return self.activities[index - 1]

    def get_all_activities(self) -> list[SecondClass]:
        """获取所有活动（如果未过期）"""
        if self.is_expired():
            return []
        return self.activities

    def parse_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        """
        解析序号字符串
        
        支持的格式：
        - "1,2,3" -> [1, 2, 3]
        - "1-5" -> [1, 2, 3, 4, 5]
        - "1,3-5,10" -> [1, 3, 4, 5, 10]
        - "全部" 或 "所有" -> 所有序号
        
        Args:
            indices_str: 序号字符串
            
        Returns:
            (有效的序号列表, 错误信息列表)
        """
        indices_str = indices_str.strip()

        # 处理"全部"或"所有"
        if indices_str in ["全部", "所有"]:
            return list(range(1, len(self.activities) + 1)), []

        indices = []
        errors = []

        # 按逗号分割
        parts = indices_str.split(",")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 检查是否是范围（如 "1-5"）
            if "-" in part:
                range_parts = part.split("-", 1)
                try:
                    start = int(range_parts[0].strip())
                    end = int(range_parts[1].strip())

                    if start > end:
                        start, end = end, start

                    # 验证范围
                    if start < 1 or end > len(self.activities):
                        errors.append(f"范围 {part} 超出有效范围（1-{len(self.activities)}）")
                        continue

                    indices.extend(range(start, end + 1))

                except ValueError:
                    errors.append(f"无法解析范围: {part}")
                    continue
            else:
                # 单个数字
                try:
                    idx = int(part)
                    if idx < 1 or idx > len(self.activities):
                        errors.append(f"序号 {idx} 超出有效范围（1-{len(self.activities)}）")
                        continue
                    indices.append(idx)
                except ValueError:
                    errors.append(f"无法解析序号: {part}")
                    continue

        # 去重并保持顺序
        seen = set()
        unique_indices = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        return unique_indices, errors


class ConfirmSession(BaseModel):
    """待确认操作会话"""
    operation: Literal["cancel", "join"]
    activity_id: str
    activity_name: str
    created_at: datetime

    def is_expired(self) -> bool:
        """是否已过期（2分钟）"""
        return datetime.now() - self.created_at > timedelta(minutes=2)

    def get_confirm_prompt(self) -> str:
        """获取确认提示文本"""
        action = "取消报名" if self.operation == "cancel" else "报名"
        return (
            f"⚠️ 请确认操作\n\n"
            f"确定要{action}「{self.activity_name}」吗？\n\n"
            f"回复「确认」执行操作\n"
            f"回复「取消」放弃操作"
        )


class UserSession:
    """用户会话管理（单用户简化版）"""

    def __init__(self) -> None:
        self.search: Optional[SearchSession] = None
        self.confirm: Optional[ConfirmSession] = None
        self.displayed_activities: Optional[DisplayedActivitiesSession] = None

    def set_search(self, keyword: str, results: list[SecondClass]) -> None:
        """设置搜索上下文"""
        self.search = SearchSession(
            keyword=keyword,
            results=results,
            created_at=datetime.now()
        )

    def clear_search(self) -> None:
        """清除搜索上下文"""
        self.search = None

    def set_confirm(self, operation: Literal["cancel", "join"],
                    activity_id: str, activity_name: str) -> None:
        """设置待确认操作"""
        self.confirm = ConfirmSession(
            operation=operation,
            activity_id=activity_id,
            activity_name=activity_name,
            created_at=datetime.now()
        )

    def clear_confirm(self) -> None:
        """清除待确认操作"""
        self.confirm = None

    def get_search_result(self, index: int) -> Optional[SecondClass]:
        """获取搜索结果（带过期检查）"""
        if not self.search:
            return None
        return self.search.get_result_by_index(index)

    def set_displayed_activities(self, activities: list[SecondClass], source: str = "unknown") -> None:
        """
        设置最近显示的活动列表
        
        Args:
            activities: 活动列表
            source: 来源标识（如 "valid", "new_activities" 等）
        """
        self.displayed_activities = DisplayedActivitiesSession(
            activities=activities,
            source=source,
            created_at=datetime.now()
        )
        logger.debug(f"保存显示的活动列表: {len(activities)} 个，来源: {source}")

    def clear_displayed_activities(self) -> None:
        """清除显示的活动列表"""
        self.displayed_activities = None

    def get_displayed_activity_by_index(self, index: int) -> Optional[SecondClass]:
        """
        根据序号获取显示的活动（带过期检查）
        
        Args:
            index: 序号（从1开始）
            
        Returns:
            SecondClass 或 None
        """
        if not self.displayed_activities:
            return None
        return self.displayed_activities.get_activity_by_index(index)

    def get_all_displayed_activities(self) -> list[SecondClass]:
        """
        获取所有显示的活动（带过期检查）
        
        Returns:
            活动列表，如果过期则返回空列表
        """
        if not self.displayed_activities:
            return []
        return self.displayed_activities.get_all_activities()

    def parse_displayed_indices(self, indices_str: str) -> tuple[list[int], list[str]]:
        """
        解析显示活动的序号字符串
        
        Args:
            indices_str: 序号字符串（如 "1,2-5,10" 或 "全部"）
            
        Returns:
            (有效的序号列表, 错误信息列表)
        """
        if not self.displayed_activities:
            return [], ["没有可操作的最近活动列表"]
        return self.displayed_activities.parse_indices(indices_str)

    def check_confirm(self, response: str) -> Optional[tuple[str, str]]:
        """
        检查确认响应
        
        Args:
            response: 用户响应文本
            
        Returns:
            (operation, activity_id) 如果确认执行
            None 如果取消或无效响应
        """
        if not self.confirm or self.confirm.is_expired():
            return None

        if response == "确认":
            result = (self.confirm.operation, self.confirm.activity_id)
            self.clear_confirm()
            return result
        elif response == "取消":
            self.clear_confirm()
            return None

        return None  # 无效响应
