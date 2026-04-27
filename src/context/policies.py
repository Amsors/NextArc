"""上下文过期策略。"""

from datetime import timedelta

from .models import ContextType

DEFAULT_CONTEXT_TTLS = {
    ContextType.SEARCH_RESULT: timedelta(minutes=5),
    ContextType.CONFIRMATION: timedelta(minutes=2),
    ContextType.DISPLAYED_ACTIVITIES: timedelta(minutes=10),
}


def get_default_ttl(context_type: ContextType) -> timedelta | None:
    return DEFAULT_CONTEXT_TTLS.get(context_type)
