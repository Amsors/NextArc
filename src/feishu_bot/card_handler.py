"""卡片交互处理器"""

import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING

from pyustc.young import Status

from src.core import SecondClassFilter
from src.core.services import ActivityUpdateService, EnrollmentService, EnrollmentStatus
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import AppContext
    from src.core import UserPreferenceManager, AuthManager
    from src.feishu_bot import FeishuBot

logger = get_logger("feishu.card_handler")


class CardActionHandler:
    def __init__(
        self,
        app_context: "AppContext",
        bot_getter: Callable[[], "FeishuBot | None"] | None = None,
    ):
        self.app_context = app_context
        self._bot_getter = bot_getter or (lambda: None)

    @property
    def _user_preference_manager(self) -> "UserPreferenceManager | None":
        return self.app_context.preference_manager

    @property
    def _auth_manager(self) -> "AuthManager | None":
        return self.app_context.auth_manager

    @property
    def _bot(self) -> "FeishuBot | None":
        return self._bot_getter()

    @property
    def _activity_update_service(self) -> ActivityUpdateService:
        return self.app_context.activity_update_service

    @property
    def _enrollment_service(self) -> EnrollmentService:
        return self.app_context.enrollment_service

    def _get_activity_update_service(self) -> ActivityUpdateService:
        return self._activity_update_service

    def _get_enrollment_service(self) -> EnrollmentService:
        return self._enrollment_service

    async def handle(self, action_value: dict, open_message_id: str) -> dict:
        action = action_value.get("action")
        activity_id = action_value.get("activity_id")
        activity_name = action_value.get("activity_name", "未知活动")

        if not action or (action != "menu_cmd" and not activity_id):
            return {
                "toast": {
                    "type": "error",
                    "content": "无效的操作参数"
                }
            }

        logger.info(f"处理卡片交互: action={action}, activity_id={activity_id}")

        if action == "toggle_ignore":
            return await self._handle_toggle_ignore(activity_id, activity_name, open_message_id)
        elif action == "toggle_interested":
            return await self._handle_toggle_interested(activity_id, activity_name, open_message_id)
        elif action == "join":
            return await self._handle_join(activity_id, activity_name)
        elif action == "view_children":
            return await self._handle_view_children(activity_id, activity_name)
        elif action == "cancel":
            return await self._handle_cancel(activity_id, activity_name)
        elif action == "menu_cmd":
            return await self._handle_menu_cmd(action_value)
        else:
            return {
                "toast": {
                    "type": "error",
                    "content": f"未知的操作类型: {action}"
                }
            }

    async def _handle_toggle_ignore(
            self,
            activity_id: str,
            activity_name: str,
            open_message_id: str
    ) -> dict:
        if not self._user_preference_manager:
            return {
                "toast": {
                    "type": "error",
                    "content": "用户偏好管理器未初始化"
                }
            }

        try:
            success, is_now_ignored = await self._user_preference_manager.toggle_ignored_activity(activity_id)

            if not success:
                return {
                    "toast": {
                        "type": "error",
                        "content": "操作失败，请稍后重试"
                    }
                }

            if is_now_ignored:
                toast_content = f"已将「{activity_name}」加入不感兴趣列表"
            else:
                toast_content = f"已将「{activity_name}」移出不感兴趣列表"

            logger.info(f"切换不感兴趣状态成功: {activity_name}, is_ignored={is_now_ignored}")

            return {
                "toast": {
                    "type": "success",
                    "content": toast_content
                }
            }

        except Exception as e:
            logger.error(f"切换不感兴趣状态失败: {e}")
            return {
                "toast": {
                    "type": "error",
                    "content": f"操作失败: {str(e)}"
                }
            }

    async def _handle_toggle_interested(
            self,
            activity_id: str,
            activity_name: str,
            open_message_id: str
    ) -> dict:
        if not self._user_preference_manager:
            return {
                "toast": {
                    "type": "error",
                    "content": "用户偏好管理器未初始化"
                }
            }

        try:
            success, is_now_interested = await self._user_preference_manager.toggle_interested_activity(activity_id)

            if not success:
                return {
                    "toast": {
                        "type": "error",
                        "content": "操作失败，请稍后重试"
                    }
                }

            if is_now_interested:
                toast_content = f"已将「{activity_name}」标记为感兴趣"
            else:
                toast_content = f"已将「{activity_name}」移出感兴趣列表"

            logger.info(f"切换感兴趣状态成功: {activity_name}, is_interested={is_now_interested}")

            return {
                "toast": {
                    "type": "success",
                    "content": toast_content
                }
            }

        except Exception as e:
            logger.error(f"切换感兴趣状态失败: {e}")
            return {
                "toast": {
                    "type": "error",
                    "content": f"操作失败: {str(e)}"
                }
            }

    async def _handle_join(self, activity_id: str, activity_name: str) -> dict:
        if not self._auth_manager or not self._bot:
            return {
                "toast": {
                    "type": "error",
                    "content": "服务未初始化，请稍后重试"
                }
            }

        logger.info(f"执行卡片报名: {activity_name} ({activity_id})")

        try:
            result = await self._get_enrollment_service().join_activity(
                activity_id,
                activity_name,
                user_id=self._bot.user_session.user_id if self._bot else None,
                force=False,
                auto_cancel=False,
                precheck_applyable=False,
            )

            if result.status == EnrollmentStatus.ALREADY_APPLIED:
                await self._bot.send_text(result.message)
                return {
                    "toast": {
                        "type": "info",
                        "content": "您已报名该活动"
                    }
                }

            if result.status == EnrollmentStatus.NOT_APPLYABLE:
                status_text = (
                    result.activity.status.text
                    if result.activity and result.activity.status
                    else "未知"
                )
                message = (
                    f"报名失败\n\n"
                    f"活动：{activity_name}\n"
                    f"原因：当前状态不可报名（{status_text}）"
                )
                await self._bot.send_text(message)
                return {
                    "toast": {
                        "type": "error",
                        "content": "当前状态不可报名"
                    }
                }

            if result.success:
                sc = result.activity
                success_message = (
                    f"报名成功\n\n"
                    f"活动：{activity_name}\n"
                    f"时间：{sc.hold_time.start.strftime('%m-%d(%a) %H:%M') if sc and sc.hold_time else '待定'} ~ "
                    f"{sc.hold_time.end.strftime('%m-%d(%a) %H:%M') if sc and sc.hold_time else '待定'}\n"
                    f"{result.calendar_message}"
                )
                await self._bot.send_text(success_message)
                logger.info(f"卡片报名成功: {activity_name}")
                return {
                    "toast": {
                        "type": "success",
                        "content": "报名成功"
                    }
                }

            fail_message = (
                f"报名失败\n\n"
                f"活动：{activity_name}\n"
                f"原因：活动不可报名或名额已满"
            )
            await self._bot.send_text(fail_message)
            logger.warning(f"卡片报名失败: {activity_name}")
            return {
                "toast": {
                    "type": "error",
                    "content": "报名失败，名额已满或已结束"
                }
            }

        except Exception as e:
            logger.error(f"卡片报名失败: {e}")
            error_message = (
                f"报名失败\n\n"
                f"活动：{activity_name}\n"
                f"错误：{str(e)}"
            )
            try:
                await self._bot.send_text(error_message)
            except Exception as send_err:
                logger.error(f"发送报名失败消息失败: {send_err}")

            return {
                "toast": {
                    "type": "error",
                    "content": f"报名失败: {str(e)[:50]}"
                }
            }

    async def _handle_view_children(self, activity_id: str, activity_name: str) -> dict:
        if not self._auth_manager or not self._bot:
            return {
                "toast": {
                    "type": "error",
                    "content": "服务未初始化，请稍后重试"
                }
            }

        logger.info(f"查看系列活动子活动: {activity_name} ({activity_id})")

        try:
            sc, children = await self._get_activity_update_service().fetch_children(activity_id)

            if not sc.is_series:
                return {
                    "toast": {
                        "type": "error",
                        "content": "该活动不是系列活动"
                    }
                }

            filter = SecondClassFilter().exclude_status([
                Status.ABNORMAL,
                Status.APPLY_ENDED,
                Status.HOUR_PUBLIC,
                Status.HOUR_APPEND_PUBLIC,
                Status.PUBLIC_ENDED,
                Status.HOUR_APPLYING,
                Status.HOUR_APPROVED,
                Status.HOUR_REJECTED,
                Status.FINISHED,
            ])

            children = filter(children)

            if not children:
                await self._bot.send_text(f'系列活动「{activity_name}」暂无可报名的子活动')
                return {
                    "toast": {
                        "type": "info",
                        "content": "该系列活动暂无子活动"
                    }
                }

            update_result = await self._get_activity_update_service().update_activities(
                children,
                continue_on_error=True,
            )
            if update_result.failed:
                logger.warning(f"子活动深度更新失败 {update_result.failed_count} 个")

            from src.utils.formatter import build_activity_card, CardButtonConfig

            ignored_ids = set()
            if self._user_preference_manager:
                ignored_ids = await self._user_preference_manager.get_all_ignored_ids()

            max_per_card = self.app_context.settings.feishu.max_activities_per_card

            button_config = CardButtonConfig()

            total = len(children)
            if total <= max_per_card:
                card_content = build_activity_card(
                    children,
                    title=f'系列活动「{activity_name}」的子活动',
                    ignored_ids=ignored_ids,
                    button_config=button_config
                )
                await self._bot.send_card(card_content)
            else:
                batches = (total + max_per_card - 1) // max_per_card
                for batch_idx in range(batches):
                    start = batch_idx * max_per_card
                    end = min(start + max_per_card, total)
                    batch_children = children[start:end]
                    start_index = start + 1

                    batch_title = f'系列活动「{activity_name}」的子活动（{batch_idx + 1}/{batches}）'

                    card_content = build_activity_card(
                        batch_children,
                        title=batch_title,
                        ignored_ids=ignored_ids,
                        start_index=start_index,
                        button_config=button_config
                    )
                    await self._bot.send_card(card_content)

                    if batch_idx < batches - 1:
                        import asyncio
                        await asyncio.sleep(0.5)

            logger.info(f"成功发送系列活动「{activity_name}」的 {len(children)} 个子活动")

            return {
                "toast": {
                    "type": "success",
                    "content": f"已发送 {len(children)} 个子活动"
                }
            }

        except Exception as e:
            traceback.print_exc()
            logger.error(f"查看子活动失败: {e}")
            error_message = (
                f"查看子活动失败\n\n"
                f"系列活动：{activity_name}\n"
                f"错误：{str(e)}"
            )
            try:
                await self._bot.send_text(error_message)
            except Exception as send_err:
                logger.error(f"发送查看子活动失败消息失败: {send_err}")

            return {
                "toast": {
                    "type": "error",
                    "content": f"查看子活动失败: {str(e)[:50]}"
                }
            }

    async def _handle_cancel(self, activity_id: str, activity_name: str) -> dict:
        if not self._auth_manager or not self._bot:
            return {
                "toast": {
                    "type": "error",
                    "content": "服务未初始化，请稍后重试"
                }
            }

        logger.info(f"执行卡片取消报名: {activity_name} ({activity_id})")

        try:
            result = await self._get_enrollment_service().cancel_activity(activity_id, activity_name)

            if result.success:
                success_message = (
                    f"取消报名成功\n\n"
                    f"活动：{activity_name}\n"
                )
                await self._bot.send_text(success_message)
                logger.info(f"卡片取消报名成功: {activity_name}")
                return {
                    "toast": {
                        "type": "success",
                        "content": "取消报名成功"
                    }
                }

            fail_message = (
                f"取消报名失败\n\n"
                f"活动：{activity_name}\n"
                f"原因：无法取消报名，请检查活动状态"
            )
            await self._bot.send_text(fail_message)
            logger.warning(f"卡片取消报名失败: {activity_name}")
            return {
                "toast": {
                    "type": "error",
                    "content": "取消报名失败，请检查活动状态"
                }
            }

        except Exception as e:
            logger.error(f"卡片取消报名失败: {e}")
            error_message = (
                f"取消报名失败\n\n"
                f"活动：{activity_name}\n"
                f"错误：{str(e)}"
            )
            try:
                await self._bot.send_text(error_message)
            except Exception as send_err:
                logger.error(f"发送取消报名失败消息失败: {send_err}")

            return {
                "toast": {
                    "type": "error",
                    "content": f"取消报名失败: {str(e)[:50]}"
                }
            }

    async def _handle_menu_cmd(self, action_value: dict) -> dict:
        """将菜单按钮转回现有文本指令入口。"""
        if not self._bot or not self._bot.message_handler:
            return {
                "toast": {
                    "type": "error",
                    "content": "服务未就绪"
                }
            }

        cmd = action_value.get("cmd")
        args = action_value.get("args") or []

        if not cmd:
            return {
                "toast": {
                    "type": "error",
                    "content": "无效的菜单命令"
                }
            }

        command_text = f"/{cmd}"
        if args:
            command_text += " " + " ".join(str(arg) for arg in args)

        logger.info(f"执行菜单命令: {command_text}")

        try:
            await self._bot.message_handler(command_text, self._bot.user_session)
        except Exception as e:
            logger.error(f"执行菜单命令失败: {e}")
            return {
                "toast": {
                    "type": "error",
                    "content": f"执行失败: {str(e)[:50]}"
                }
            }

        return {
            "toast": {
                "type": "success",
                "content": f"已执行 {command_text}"
            }
        }
