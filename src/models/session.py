"""用户会话身份与上下文入口。"""

from src.context import (
    ConfirmationPayload,
    ContextManager,
    ContextType,
    DisplayedActivitiesPayload,
    SearchResultPayload,
)

ConfirmSession = ConfirmationPayload
SearchSession = SearchResultPayload
DisplayedActivitiesSession = DisplayedActivitiesPayload


class UserSession:
    """单实例会话。

    业务上下文由 ContextManager 承载；这里仅保留飞书交互需要的身份字段。
    """

    def __init__(self, context_manager: ContextManager | None = None) -> None:
        self.context_manager = context_manager or ContextManager()
        self.user_id: str | None = None

    def clear_identity(self) -> None:
        self.user_id = None

    async def clear_context(self) -> None:
        await self.context_manager.clear()

    async def clear_search(self) -> None:
        await self.context_manager.clear(ContextType.SEARCH_RESULT)
