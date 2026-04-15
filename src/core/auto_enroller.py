"""自动报名器 - 监控感兴趣的活动并自动报名"""

import asyncio
import time
from typing import TYPE_CHECKING, Optional

from pyustc.young import SecondClass, Status

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core import AuthManager, UserPreferenceManager
    from src.feishu_bot import FeishuBot

logger = get_logger("auto_enroller")


class AutoEnroller:
    """自动报名器 - 每5分钟检查感兴趣的活动，有可报名名额时自动报名"""

    def __init__(
        self,
        auth_manager: "AuthManager",
        user_preference_manager: "UserPreferenceManager",
        bot: Optional["FeishuBot"] = None,
        interval_minutes: int = 5,
    ):
        self._auth_manager = auth_manager
        self._user_preference_manager = user_preference_manager
        self._bot = bot
        self._interval_minutes = interval_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def set_bot(self, bot: "FeishuBot") -> None:
        """设置飞书机器人实例（用于发送通知）"""
        self._bot = bot

    def start(self) -> None:
        """启动自动报名监控"""
        if self._running:
            logger.warning("自动报名器已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"自动报名器已启动，监控间隔: {self._interval_minutes}分钟")

    def stop(self) -> None:
        """停止自动报名监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("自动报名器已停止")

    async def _run_loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                await self._check_and_enroll()
            except Exception as e:
                logger.error(f"自动报名检查失败: {e}")

            # 等待下一次检查
            await asyncio.sleep(self._interval_minutes * 60)

    async def _check_and_enroll(self) -> None:
        """检查感兴趣的活动并尝试报名"""
        # 获取所有感兴趣的活动ID
        interested_ids = await self._user_preference_manager.get_all_interested_ids()
        if not interested_ids:
            logger.debug("没有感兴趣的活动需要监控")
            return

        logger.info(f"开始检查 {len(interested_ids)} 个感兴趣的活动")

        async with self._auth_manager.create_session_once():
            for activity_id in interested_ids:
                if not self._running:
                    break

                try:
                    await self._try_enroll_activity(activity_id)
                except Exception as e:
                    logger.error(f"尝试报名活动 {activity_id} 失败: {e}")

    async def _try_enroll_activity(self, activity_id: str) -> bool:
        """尝试报名单个活动，成功返回True"""
        try:
            sc = SecondClass(activity_id, {})
            await sc.update()

            # 检查是否已报名
            if sc.applied:
                logger.info(f"活动 {sc.name} 已报名，从感兴趣列表移除")
                await self._user_preference_manager.remove_interested_activity(activity_id)
                return False

            # 检查是否可报名
            if sc.status != Status.APPLYING and sc.status != Status.PUBLISHED:
                logger.debug(f"活动 {sc.name} 当前不可报名（状态: {sc.status.text if sc.status else '未知'}）")
                return False

            # 尝试报名
            logger.info(f"尝试报名活动: {sc.name}")

            if sc.need_sign_info:
                from pyustc.young.second_class import SignInfo
                sign_info = await SignInfo.get_self()
                result = await sc.apply(force=False, auto_cancel=False, sign_info=sign_info)
            else:
                result = await sc.apply(force=False, auto_cancel=False)

            if result:
                # 报名成功
                logger.info(f"自动报名成功: {sc.name}")

                # 从感兴趣列表移除
                await self._user_preference_manager.remove_interested_activity(activity_id)

                # 发送通知
                await self._send_success_notification(sc)
                return True
            else:
                logger.debug(f"活动 {sc.name} 报名失败（可能名额已满）")
                return False

        except Exception as e:
            logger.error(f"报名活动 {activity_id} 时出错: {e}")
            return False

    async def _send_success_notification(self, sc: SecondClass) -> None:
        """发送报名成功通知"""
        if not self._bot:
            logger.warning("飞书机器人未设置，无法发送通知")
            return

        try:
            # 构建通知消息
            time_str = "待定"
            if sc.hold_time:
                start = sc.hold_time.start.strftime("%m-%d(%a) %H:%M") if sc.hold_time.start else "待定"
                end = sc.hold_time.end.strftime("%m-%d(%a) %H:%M") if sc.hold_time.end else "待定"
                time_str = f"{start} ~ {end}"

            place_str = "待定"
            if hasattr(sc, 'place_info') and sc.place_info:
                place_str = sc.place_info

            message = (
                f"🎉 自动报名成功！\n\n"
                f"活动：{sc.name}\n"
                f"时间：{time_str}\n"
                f"地点：{place_str}\n\n"
                f"已自动从感兴趣列表移除"
            )

            await self._bot.send_text(message)
            logger.info(f"已发送报名成功通知: {sc.name}")

        except Exception as e:
            logger.error(f"发送报名成功通知失败: {e}")
