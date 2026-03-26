"""卡片交互处理器

处理飞书消息卡片中的按钮点击事件，包括：
- 切换不感兴趣状态
- 执行报名操作
"""

from typing import TYPE_CHECKING, Optional

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core import UserPreferenceManager, AuthManager
    from src.feishu_bot import FeishuBot

logger = get_logger("feishu.card_handler")


class CardActionHandler:
    """
    卡片交互处理器

    处理用户在卡片中点击按钮的交互事件。
    """

    def __init__(self):
        self._user_preference_manager: Optional["UserPreferenceManager"] = None
        self._auth_manager: Optional["AuthManager"] = None
        self._bot: Optional["FeishuBot"] = None

    def set_dependencies(
            self,
            user_preference_manager: "UserPreferenceManager",
            auth_manager: "AuthManager",
            bot: "FeishuBot"
    ) -> None:
        """
        设置依赖组件

        Args:
            user_preference_manager: 用户偏好管理器
            auth_manager: 认证管理器
            bot: 飞书机器人实例
        """
        self._user_preference_manager = user_preference_manager
        self._auth_manager = auth_manager
        self._bot = bot

    async def handle(self, action_value: dict, open_message_id: str) -> dict:
        """
        处理卡片交互事件

        Args:
            action_value: 按钮的 value 数据
            open_message_id: 消息ID（用于更新卡片）

        Returns:
            响应数据字典（包含 toast 和可选的 card）
        """
        action = action_value.get("action")
        activity_id = action_value.get("activity_id")
        activity_name = action_value.get("activity_name", "未知活动")

        if not action or not activity_id:
            return {
                "toast": {
                    "type": "error",
                    "content": "无效的操作参数"
                }
            }

        logger.info(f"处理卡片交互: action={action}, activity_id={activity_id}")

        if action == "toggle_ignore":
            return await self._handle_toggle_ignore(activity_id, activity_name, open_message_id)
        elif action == "join":
            return await self._handle_join(activity_id, activity_name)
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
        """
        处理切换不感兴趣状态

        Args:
            activity_id: 活动ID
            activity_name: 活动名称
            open_message_id: 消息ID

        Returns:
            响应数据字典
        """
        if not self._user_preference_manager:
            return {
                "toast": {
                    "type": "error",
                    "content": "用户偏好管理器未初始化"
                }
            }

        try:
            # 切换状态
            success, is_now_ignored = await self._user_preference_manager.toggle_ignored_activity(activity_id)

            if not success:
                return {
                    "toast": {
                        "type": "error",
                        "content": "操作失败，请稍后重试"
                    }
                }

            # 构建响应
            if is_now_ignored:
                toast_content = f"已将「{activity_name}」加入不感兴趣列表"
                button_text = "已忽略"
            else:
                toast_content = f"已将「{activity_name}」移出不感兴趣列表"
                button_text = "不感兴趣"

            logger.info(f"切换不感兴趣状态成功: {activity_name}, is_ignored={is_now_ignored}")

            # 只返回 toast 提示，不更新卡片
            # 卡片更新需要重新构建完整卡片，这在当前架构下较复杂
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

    async def _handle_join(self, activity_id: str, activity_name: str) -> dict:
        """
        处理报名操作

        Args:
            activity_id: 活动ID
            activity_name: 活动名称

        Returns:
            响应数据字典
        """
        if not self._auth_manager or not self._bot:
            return {
                "toast": {
                    "type": "error",
                    "content": "服务未初始化，请稍后重试"
                }
            }

        logger.info(f"执行卡片报名: {activity_name} ({activity_id})")

        try:
            # 导入 pyustc 相关模块
            from pyustc.young import SecondClass, Status

            # 使用认证会话执行报名
            async with self._auth_manager.create_session_once():
                # 获取活动实例
                sc = SecondClass(activity_id, {})
                await sc.update()

                # 检查是否已报名
                if sc.applied:
                    message = f"您已经报名了「{activity_name}」"
                    await self._bot.send_text(message)
                    return {
                        "toast": {
                            "type": "info",
                            "content": "您已报名该活动"
                        }
                    }

                # 检查是否可报名
                if sc.status != Status.APPLYING and sc.status != Status.PUBLISHED:
                    message = (
                        f"报名失败\n\n"
                        f"活动：{activity_name}\n"
                        f"原因：当前状态不可报名（{sc.status.text if sc.status else '未知'}）"
                    )
                    await self._bot.send_text(message)
                    return {
                        "toast": {
                            "type": "error",
                            "content": "当前状态不可报名"
                        }
                    }

                # 执行报名
                if sc.need_sign_info:
                    from pyustc.young.second_class import SignInfo
                    sign_info = await SignInfo.get_self()
                    result = await sc.apply(force=False, auto_cancel=False, sign_info=sign_info)
                else:
                    result = await sc.apply(force=False, auto_cancel=False)

                if result:
                    # 报名成功
                    success_message = (
                        f"报名成功\n\n"
                        f"活动：{activity_name}\n"
                        f"时间：{sc.hold_time.start.strftime('%m-%d(%a) %H:%M') if sc.hold_time else '待定'} ~ "
                        f"{sc.hold_time.end.strftime('%m-%d(%a) %H:%M') if sc.hold_time else '待定'}\n\n"
                    )
                    await self._bot.send_text(success_message)
                    logger.info(f"卡片报名成功: {activity_name}")
                    return {
                        "toast": {
                            "type": "success",
                            "content": "报名成功"
                        }
                    }
                else:
                    # 报名失败
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
