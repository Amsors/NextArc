"""扫描相关定时任务辅助。"""

from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from src.core.events.version_events import VersionUpdateEvent
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from src.core.events import EventBus
    from src.core.version_checker import VersionChecker

logger = get_logger("scanning.scheduler")


class VersionScheduler:
    """把版本检查调度从 ActivityScanner 中拆出。"""

    def __init__(
        self,
        scheduler: "AsyncIOScheduler",
        version_checker: "VersionChecker | None",
        event_bus: "EventBus | None",
    ):
        self.scheduler = scheduler
        self.version_checker = version_checker
        self.event_bus = event_bus

    def add_job(self) -> bool:
        logger.info(f"检查版本检查器: version_checker={self.version_checker is not None}")
        if self.version_checker:
            logger.info(f"版本检查器 enabled={self.version_checker.enabled}")

        if not self.version_checker or not self.version_checker.enabled:
            logger.info("版本检查任务未添加（未启用或未初始化）")
            return False

        config = self.version_checker.config
        logger.info("正在添加版本检查任务...")
        logger.info(
            "配置: day_of_week=%s, hour=%s, minute=%s",
            config.day_of_week,
            config.hour,
            config.minute,
        )

        self.scheduler.add_job(
            self.check_version,
            trigger=CronTrigger(
                day_of_week=config.day_of_week,
                hour=config.hour,
                minute=config.minute,
            ),
            id="version_check",
            replace_existing=True,
            max_instances=1,
        )
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday_name = weekday_names[config.day_of_week]
        logger.info(f"版本检查已启动，每周 {weekday_name} {config.hour:02d}:{config.minute:02d}")
        return True

    async def check_version(self) -> None:
        logger.info("定时任务触发，开始检查版本更新...")

        if not self.version_checker:
            logger.warning("版本检查器未初始化，跳过检查")
            return

        try:
            logger.info("正在检查更新...")
            result = await self.version_checker.check_for_updates()

            if result is None:
                logger.info("已是最新版本或检查失败（返回 None）")
            elif result.commits_behind > 0:
                logger.info(f"发现新版本！落后 {result.commits_behind} 个 commit")
                logger.info(
                    "当前版本: %s, 最新版本: %s",
                    result.current_sha[:7],
                    result.latest_sha[:7],
                )
                if self.event_bus:
                    event = VersionUpdateEvent(
                        current_sha=result.current_sha,
                        latest_sha=result.latest_sha,
                        commits_behind=result.commits_behind,
                        new_commits=result.new_commits,
                        repo_url=result.repo_url,
                    )
                    await self.event_bus.publish(event)
                    logger.info("已发布 VersionUpdateEvent 事件")
                else:
                    logger.warning("EventBus 未设置，无法发布事件")
            else:
                logger.info("当前已是最新版本，无需通知")

        except Exception as e:
            logger.error(f"版本检查失败: {e}", exc_info=True)

        logger.info("检查完成")
