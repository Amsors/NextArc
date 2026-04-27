"""活动筛选结果。"""

from dataclasses import dataclass, field

from pyustc.young import SecondClass

from src.models.filter_result import FilteredActivity


@dataclass
class FilterPipelineResult:
    """统一筛选管线输出。"""

    kept: list[SecondClass]
    filtered: dict[str, list[FilteredActivity]] = field(default_factory=dict)
    restored: list[SecondClass] = field(default_factory=list)
    ai_keep_reasons: dict[str, str] = field(default_factory=dict)
    overlap_reasons: dict[str, str] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)

    def non_empty_filtered(self) -> dict[str, list[FilteredActivity]]:
        return {
            filter_type: activities
            for filter_type, activities in self.filtered.items()
            if activities
        }
