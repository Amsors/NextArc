"""上下文存储实现。"""

from .models import ContextRecord, ContextType


class InMemoryContextStore:
    """当前单实例部署使用的内存上下文存储。"""

    def __init__(self) -> None:
        self._records: dict[ContextType, ContextRecord] = {}

    async def set(self, record: ContextRecord) -> None:
        self.set_sync(record)

    def set_sync(self, record: ContextRecord) -> None:
        self._records[record.type] = record

    async def get(self, context_type: ContextType) -> ContextRecord | None:
        return self.get_sync(context_type)

    def get_sync(self, context_type: ContextType) -> ContextRecord | None:
        return self._records.get(context_type)

    async def clear(self, context_type: ContextType | None = None) -> None:
        self.clear_sync(context_type)

    def clear_sync(self, context_type: ContextType | None = None) -> None:
        if context_type is None:
            self._records.clear()
            return
        self._records.pop(context_type, None)

    def items(self) -> list[tuple[ContextType, ContextRecord]]:
        return list(self._records.items())
