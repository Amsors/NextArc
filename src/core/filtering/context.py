"""活动筛选上下文。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pyustc.young import Status


@dataclass
class FilterContext:
    """一次活动筛选运行所需的显式配置。"""

    latest_db: Path
    enable_filters: bool = True
    include_interested_restore: bool = True
    use_ai_cache: bool = True
    force_ai_review: bool = False
    ignore_overlap: bool = False
    source: str = "unknown"
    allowed_statuses: Iterable[Status | int] | None = None
    apply_enrolled_filter: bool = True

    def allowed_status_codes(self) -> set[int] | None:
        if self.allowed_statuses is None:
            return None

        codes: set[int] = set()
        for status in self.allowed_statuses:
            code = getattr(status, "code", status)
            codes.add(int(code))
        return codes
