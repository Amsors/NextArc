"""已报名活动筛选器"""

from typing import Optional

from pyustc.young import SecondClass

from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger

logger = get_logger("enrolled_filter")


class EnrolledFilter:
    def __init__(self, enrolled_ids: Optional[set[str]] = None):
        self.enrolled_ids = enrolled_ids or set()

    def set_enrolled_ids(self, enrolled_ids: set[str]) -> None:
        self.enrolled_ids = enrolled_ids

    def filter_activities(
            self,
            activities: list[SecondClass]
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        if not activities:
            return [], []

        if not self.enrolled_ids:
            logger.debug("没有已报名活动记录，跳过已报名筛选")
            return activities, []

        logger.info(f"开始已报名筛选，共 {len(activities)} 个活动，已报名记录 {len(self.enrolled_ids)} 个...")

        passed = []
        filtered: list[FilteredActivity] = []

        for activity in activities:
            activity_id = getattr(activity, 'id', None)
            if activity_id is None and isinstance(activity, dict):
                activity_id = activity.get('id')

            if activity_id and activity_id in self.enrolled_ids:
                filtered.append(FilteredActivity(
                    activity=activity,
                    reason="已报名该活动",
                    filter_type="enrolled"
                ))
                logger.debug(f"活动 '{activity.name}' 已报名，过滤")
            else:
                passed.append(activity)

        logger.info(f"已报名筛选完成：{len(passed)} 个通过，{len(filtered)} 个已报名被过滤")

        return passed, filtered

    @staticmethod
    async def get_enrolled_ids_from_db(db_path) -> set[str]:
        from src.core.repositories import ActivityRepository

        return await ActivityRepository().list_enrolled_ids(db_path)
