"""用户会话数据模型"""

from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pyustc.young import SecondClass


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
