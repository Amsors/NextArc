"""报名与取消报名用例服务。"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from pyustc.young import SecondClass, Status
from pyustc.young.second_class import SignInfo

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core.auth_manager import AuthManager
    from src.core.db_manager import DatabaseManager

logger = get_logger("service.enrollment")


class EnrollmentStatus(str, Enum):
    SUCCESS = "success"
    ALREADY_APPLIED = "already_applied"
    NOT_APPLYABLE = "not_applyable"
    FAILED = "failed"


@dataclass
class EnrollmentResult:
    """报名或取消报名结果。"""

    status: EnrollmentStatus
    activity_id: str
    activity_name: str
    message: str
    activity: SecondClass | None = None
    calendar_message: str = ""
    error: Exception | None = None

    @property
    def success(self) -> bool:
        return self.status == EnrollmentStatus.SUCCESS


class EnrollmentService:
    """统一封装报名、取消报名和报名后的日历同步。

    报名或取消成功后会增量维护最新活动快照中的已报名表。
    """

    def __init__(
        self,
        auth_manager: "AuthManager",
        app_id: str = "",
        app_secret: str = "",
        calendar_sync_enabled: bool = True,
        db_manager: "DatabaseManager | None" = None,
    ):
        self.auth_manager = auth_manager
        self.app_id = app_id
        self.app_secret = app_secret
        self.calendar_sync_enabled = calendar_sync_enabled
        self.db_manager = db_manager

    async def join_activity(
        self,
        activity_id: str,
        activity_name: str | None = None,
        *,
        user_id: str | None = None,
        force: bool = True,
        auto_cancel: bool = False,
        precheck_applyable: bool = True,
        sync_calendar: bool = True,
    ) -> EnrollmentResult:
        display_name = activity_name or activity_id
        logger.info(f"执行报名: {display_name} ({activity_id})")

        try:
            async with self.auth_manager.create_session_once():
                activity = SecondClass(activity_id, {})
                await activity.update()
                display_name = activity_name or activity.name

                if activity.applied:
                    return EnrollmentResult(
                        status=EnrollmentStatus.ALREADY_APPLIED,
                        activity_id=activity_id,
                        activity_name=display_name,
                        activity=activity,
                        message=f"您已经报名了「{display_name}」",
                    )

                if activity.status not in (Status.APPLYING, Status.PUBLISHED):
                    status_text = activity.status.text if activity.status else "未知"
                    return EnrollmentResult(
                        status=EnrollmentStatus.NOT_APPLYABLE,
                        activity_id=activity_id,
                        activity_name=display_name,
                        activity=activity,
                        message=f"「{display_name}」当前状态不可报名\n状态：{status_text}",
                    )

                if precheck_applyable and not activity.applyable:
                    status_text = activity.status.text if activity.status else "未知"
                    return EnrollmentResult(
                        status=EnrollmentStatus.NOT_APPLYABLE,
                        activity_id=activity_id,
                        activity_name=display_name,
                        activity=activity,
                        message=f"「{display_name}」当前不可报名\n状态：{status_text}",
                    )

                if activity.need_sign_info:
                    sign_info = await SignInfo.get_self()
                    applied = await activity.apply(
                        force=force,
                        auto_cancel=auto_cancel,
                        sign_info=sign_info,
                    )
                else:
                    applied = await activity.apply(force=force, auto_cancel=auto_cancel)

                logger.info(f"apply() 返回值: {applied}")
                if not applied:
                    return EnrollmentResult(
                        status=EnrollmentStatus.FAILED,
                        activity_id=activity_id,
                        activity_name=display_name,
                        activity=activity,
                        message="报名失败：活动不可报名或名额已满",
                    )

                activity.data["booleanRegistration"] = 1

            await self._upsert_enrolled_snapshot(activity)

            calendar_message = ""
            if sync_calendar and self.app_id and self.app_secret:
                from src.feishu_bot.calendar_service import sync_secondclass_to_calendar

                calendar_message = await sync_secondclass_to_calendar(
                    app_id=self.app_id,
                    app_secret=self.app_secret,
                    user_id=user_id,
                    sc=activity,
                    enabled=self.calendar_sync_enabled,
                )

            logger.info(f"报名成功: {display_name}")
            return EnrollmentResult(
                status=EnrollmentStatus.SUCCESS,
                activity_id=activity_id,
                activity_name=display_name,
                activity=activity,
                calendar_message=calendar_message,
                message=f"已成功报名「{display_name}」{calendar_message}",
            )
        except Exception as e:
            logger.error(f"报名失败: {e}")
            return EnrollmentResult(
                status=EnrollmentStatus.FAILED,
                activity_id=activity_id,
                activity_name=display_name,
                message=str(e),
                error=e,
            )

    async def cancel_activity(
        self,
        activity_id: str,
        activity_name: str | None = None,
    ) -> EnrollmentResult:
        display_name = activity_name or activity_id
        logger.info(f"执行取消报名: {display_name} ({activity_id})")

        try:
            async with self.auth_manager.create_session_once():
                activity = SecondClass(activity_id, {})
                result = await activity.cancel_apply()
                logger.info(f"cancel_apply() 返回值: {result}")

                if not result:
                    return EnrollmentResult(
                        status=EnrollmentStatus.FAILED,
                        activity_id=activity_id,
                        activity_name=display_name,
                        activity=activity,
                        message="取消报名失败",
                    )

            await self._delete_enrolled_snapshot(activity_id)

            logger.info(f"取消报名成功: {display_name}")
            return EnrollmentResult(
                status=EnrollmentStatus.SUCCESS,
                activity_id=activity_id,
                activity_name=display_name,
                activity=activity,
                message=f"已成功取消报名「{display_name}」",
            )
        except Exception as e:
            logger.error(f"取消报名失败: {e}")
            return EnrollmentResult(
                status=EnrollmentStatus.FAILED,
                activity_id=activity_id,
                activity_name=display_name,
                message=str(e),
                error=e,
            )

    async def _upsert_enrolled_snapshot(self, activity: SecondClass) -> None:
        latest_db = self._get_latest_db_path()
        if latest_db is None:
            logger.warning(f"报名成功但未找到活动快照数据库，跳过已报名快照写入: {activity.id}")
            return

        from src.core.secondclass_db import SecondClassDB

        await SecondClassDB(latest_db).upsert_enrolled_secondclass(activity, deep_scaned=True)

    async def _delete_enrolled_snapshot(self, activity_id: str) -> None:
        latest_db = self._get_latest_db_path()
        if latest_db is None:
            logger.warning(f"取消报名成功但未找到活动快照数据库，跳过已报名快照删除: {activity_id}")
            return

        from src.core.secondclass_db import SecondClassDB

        await SecondClassDB(latest_db).delete_enrolled_secondclass(activity_id)

    def _get_latest_db_path(self):
        if self.db_manager is None:
            return None
        return self.db_manager.get_latest_db()
