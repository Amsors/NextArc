"""飞书机器人客户端"""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Callable, Coroutine, Optional

from lark_oapi.api.im.v1 import (
    P2ImChatAccessEventBotP2pChatEnteredV1,
    P2ImMessageMessageReadV1,
    P2ImMessageReceiveV1,
)
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as WSClient

from src.models import UserSession
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from .card_handler import CardActionHandler

logger = get_logger("feishu")


class FeishuBot:
    def __init__(
            self,
            app_id: str,
            app_secret: str,
            message_handler: Optional[Callable[[str, UserSession], Coroutine]] = None,
            chat_id: Optional[str] = None,
            card_handler: Optional["CardActionHandler"] = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = message_handler
        self.card_handler = card_handler
        self.user_session = UserSession()
        self._client: Optional[WSClient] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._chat_id: Optional[str] = chat_id if chat_id else None
        self._chat_id_configured: bool = bool(chat_id)
        self._stop_event = threading.Event()

        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._executor = ThreadPoolExecutor(max_workers=2)

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    def _create_event_handler(self) -> EventDispatcherHandler:
        builder = EventDispatcherHandler.builder("", "")

        builder.register_p2_im_message_receive_v1(self._on_message_receive)

        builder.register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
            self._on_bot_p2p_chat_entered
        )

        builder.register_p2_im_message_message_read_v1(
            self._on_message_read
        )

        builder.register_p2_card_action_trigger(self._on_card_action_trigger)

        return builder.build()

    def _on_message_read(self, event: P2ImMessageMessageReadV1) -> None:
        logger.debug(f"用户已读消息")

    def _on_card_action_trigger(self, event: P2CardActionTrigger) -> dict:
        logger.info("=" * 50)
        logger.info("收到卡片交互事件")

        try:
            logger.info(f"card_handler 是否存在: {self.card_handler is not None}")
            logger.info(f"_main_loop 是否存在: {self._main_loop is not None}")

            if not self.card_handler:
                logger.error("卡片处理器未设置")
                return {"toast": {"type": "error", "content": "服务未就绪"}}

            if not event.event:
                logger.error("事件数据为空")
                return {"toast": {"type": "error", "content": "无效的事件数据"}}

            open_message_id = ""
            if event.event.context:
                open_message_id = event.event.context.open_message_id or ""
                logger.info(f"消息ID: {open_message_id}")

            action = event.event.action
            if not action or not action.value:
                logger.error("操作数据为空")
                return {"toast": {"type": "error", "content": "无效的操作数据"}}

            action_value = action.value
            logger.info(f"操作数据: {action_value}")

            import asyncio
            if self._main_loop:
                logger.info("正在调度异步处理...")
                future = asyncio.run_coroutine_threadsafe(
                    self._async_handle_card_action(action_value, open_message_id),
                    self._main_loop
                )
                try:
                    result = future.result(timeout=2.0)
                    logger.info(f"处理完成，返回结果: {result}")
                    return result
                except Exception as e:
                    logger.error(f"处理超时或失败: {e}")
                    return {"toast": {"type": "info", "content": "处理中，请稍后..."}}
            else:
                logger.error("主事件循环未设置")
                return {"toast": {"type": "error", "content": "服务未就绪"}}

        except Exception as e:
            logger.error(f"处理卡片交互事件异常: {e}")
            import traceback
            traceback.print_exc()
            return {"toast": {"type": "error", "content": "处理失败"}}

    async def _async_handle_card_action(self, action_value: dict, open_message_id: str) -> dict:
        try:
            if self.card_handler:
                return await self.card_handler.handle(action_value, open_message_id)
            return {"toast": {"type": "error", "content": "服务未就绪"}}
        except Exception as e:
            logger.error(f"异步处理卡片交互失败: {e}")
            return {"toast": {"type": "error", "content": f"处理失败: {str(e)[:50]}"}}

    def _on_bot_p2p_chat_entered(self, event: P2ImChatAccessEventBotP2pChatEnteredV1) -> None:
        try:
            logger.info("用户进入私聊")

            if event.event and event.event.chat_id:
                chat_id = event.event.chat_id
                self._chat_id = chat_id

                if not self._chat_id_configured:
                    logger.info(f"用户进入私聊，当前 chat_id: {chat_id} （可配置到 config.yaml 的 feishu.chat_id 中）")
                else:
                    logger.info(f"记录 chat_id: {chat_id}")

        except Exception as e:
            logger.error(f"处理进入私聊事件失败: {e}")

    def _on_message_receive(self, event: P2ImMessageReceiveV1) -> None:
        try:
            if event.event and event.event.message:
                chat_id = event.event.message.chat_id
                self._chat_id = chat_id

                if not self._chat_id_configured:
                    logger.info(f"收到消息，当前 chat_id: {chat_id} （可配置到 config.yaml 的 feishu.chat_id 中）")

                if self._main_loop and self.message_handler:
                    message = event.event.message

                    if message.message_type == "text":
                        content = json.loads(message.content)
                        text = content.get("text", "").strip()

                        logger.info(f"收到消息: {text[:50]}...")

                        asyncio.run_coroutine_threadsafe(
                            self._async_handle_message(text),
                            self._main_loop
                        )

        except Exception as e:
            logger.error(f"处理消息事件失败: {e}")

    async def _async_handle_message(self, text: str):
        try:
            if self.message_handler:
                reply = await self.message_handler(text, self.user_session)
                if reply:
                    await self.send_text(reply)
        except Exception as e:
            logger.error(f"异步处理消息失败: {e}")

    def _create_ws_client(self) -> WSClient:
        event_handler = self._create_event_handler()

        return WSClient(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=event_handler,
        )

    def _run_client(self):
        try:
            logger.debug("WebSocket 线程启动")
            self._client.start()
        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"WebSocket 运行错误: {e}")

    async def send_text(self, content: str) -> bool:
        if not self._chat_id:
            logger.error("无法发送消息：未获取到 chat_id")
            return False

        try:
            from lark_oapi import Client
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            client = Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()

            body = CreateMessageRequestBody.builder() \
                .receive_id(self._chat_id) \
                .content(json.dumps({"text": content})) \
                .msg_type("text") \
                .build()

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(body) \
                .build()

            response = client.im.v1.message.create(request)

            if response.success():
                logger.debug(f"消息发送成功")
                return True
            else:
                logger.error(f"消息发送失败: {response.msg}")
                return False

        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def send_card(self, card_content: dict) -> bool:
        if not self._chat_id:
            logger.error("无法发送卡片：未获取到 chat_id")
            return False

        try:
            from lark_oapi import Client
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            client = Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()

            body = CreateMessageRequestBody.builder() \
                .receive_id(self._chat_id) \
                .content(json.dumps(card_content, ensure_ascii=False)) \
                .msg_type("interactive") \
                .build()

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(body) \
                .build()

            response = client.im.v1.message.create(request)

            if response.success():
                logger.debug("卡片发送成功")
                return True
            else:
                logger.error(f"卡片发送失败: {response.msg}")
                return False

        except Exception as e:
            logger.error(f"发送卡片异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def start(self) -> None:
        logger.info("正在启动飞书机器人...")

        self._main_loop = asyncio.get_event_loop()

        self._client = self._create_ws_client()
        self._stop_event.clear()

        try:
            self._thread = threading.Thread(target=self._run_client, daemon=True)
            self._thread.start()

            await asyncio.sleep(2)

            self._connected = True
            logger.info("飞书机器人已启动，正在监听消息...")

        except Exception as e:
            logger.error(f"启动飞书机器人失败: {e}")
            raise

    async def send_startup_message(self, message: str) -> bool:
        if not self._chat_id:
            logger.warning("无法发送启动问候：未获取到 chat_id，等待用户先发送消息")
            return False

        logger.info("发送启动问候消息到已配置的 chat_id...")
        return await self.send_text(message)

    async def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("正在关闭飞书机器人...")

            self._stop_event.set()
            self._connected = False

            self._thread.join(timeout=3)

            logger.info("飞书机器人已关闭")

    def is_connected(self) -> bool:
        return self._connected and self._thread and self._thread.is_alive()

    def get_chat_id(self) -> Optional[str]:
        return self._chat_id

    async def send_response(self, response) -> bool:
        """根据 Response 类型自动发送文本或卡片"""
        if not response:
            return True

        from src.notifications import ResponseType

        response_type = getattr(response, 'type', None)
        content = getattr(response, 'content', None)

        if response_type == ResponseType.TEXT:
            return await self.send_text(content or "")
        elif response_type == ResponseType.CARD:
            return await self.send_card(content)
        else:
            return False
