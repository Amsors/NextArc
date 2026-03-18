"""飞书机器人客户端"""

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Coroutine, Optional

from lark_oapi.api.im.v1 import (
    P2ImChatAccessEventBotP2pChatEnteredV1,
    P2ImMessageMessageReadV1,
    P2ImMessageReceiveV1,
)
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as WSClient

from src.models import UserSession
from src.utils.logger import get_logger

logger = get_logger("feishu")


class FeishuBot:
    """
    飞书机器人客户端
    
    使用 lark-oapi 建立 WebSocket 长连接，接收和发送消息
    """
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        message_handler: Optional[Callable[[str, UserSession], Coroutine]] = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = message_handler
        self.user_session = UserSession()
        self._client: Optional[WSClient] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._chat_id: Optional[str] = None
        self._stop_event = threading.Event()
        
        # 用于在主线程中执行异步代码
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        """设置主事件循环，用于在 WebSocket 线程中回调"""
        self._main_loop = loop
    
    def _create_event_handler(self) -> EventDispatcherHandler:
        """创建事件处理器"""
        builder = EventDispatcherHandler.builder("", "")
        
        # 注册消息接收事件处理器
        builder.register_p2_im_message_receive_v1(self._on_message_receive)
        
        # 注册用户进入私聊事件处理器
        builder.register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
            self._on_bot_p2p_chat_entered
        )
        
        # 注册用户已读消息事件处理器（避免报错）
        builder.register_p2_im_message_message_read_v1(
            self._on_message_read
        )
        
        return builder.build()
    
    def _on_message_read(self, event: P2ImMessageMessageReadV1) -> None:
        """处理用户已读消息事件"""
        # 静默处理，不需要回复
        logger.debug(f"用户已读消息")
    
    def _on_bot_p2p_chat_entered(self, event: P2ImChatAccessEventBotP2pChatEnteredV1) -> None:
        """处理用户进入私聊事件"""
        try:
            logger.info("用户进入私聊")
            
            # 保存 chat_id
            if event.event and event.event.chat_id:
                self._chat_id = event.event.chat_id
                logger.info(f"记录 chat_id: {self._chat_id}")
                
        except Exception as e:
            logger.error(f"处理进入私聊事件失败: {e}")
    
    def _on_message_receive(self, event: P2ImMessageReceiveV1) -> None:
        """处理收到的消息事件（同步回调，在 WebSocket 线程中执行）"""
        try:
            # 保存 chat_id
            if event.event and event.event.message:
                self._chat_id = event.event.message.chat_id
                
                # 只在主循环设置后才尝试回调
                if self._main_loop and self.message_handler:
                    # 使用主事件循环来调度异步任务
                    message = event.event.message
                    
                    # 只处理文本消息
                    if message.message_type == "text":
                        content = json.loads(message.content)
                        text = content.get("text", "").strip()
                        
                        logger.info(f"收到消息: {text[:50]}...")
                        
                        # 在主事件循环中调度处理
                        asyncio.run_coroutine_threadsafe(
                            self._async_handle_message(text),
                            self._main_loop
                        )
                        
        except Exception as e:
            logger.error(f"处理消息事件失败: {e}")
    
    async def _async_handle_message(self, text: str):
        """在主事件循环中异步处理消息"""
        try:
            if self.message_handler:
                reply = await self.message_handler(text, self.user_session)
                if reply:
                    await self.send_text(reply)
        except Exception as e:
            logger.error(f"异步处理消息失败: {e}")
    
    def _create_ws_client(self) -> WSClient:
        """创建 WebSocket 客户端"""
        event_handler = self._create_event_handler()
        
        return WSClient(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=event_handler,
        )
    
    def _run_client(self):
        """在单独线程中运行客户端"""
        try:
            logger.debug("WebSocket 线程启动")
            self._client.start()
        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"WebSocket 运行错误: {e}")
    
    async def send_text(self, content: str) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            
        Returns:
            是否发送成功
        """
        if not self._chat_id:
            logger.error("无法发送消息：未获取到 chat_id")
            return False
        
        try:
            # 使用 lark-oapi 发送消息
            from lark_oapi import Client
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
            
            # 使用 ClientBuilder 构建客户端
            client = Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()
            
            # 使用 builder 模式创建请求体
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
    
    async def start(self) -> None:
        """启动 WebSocket 连接（在单独线程中）"""
        logger.info("正在启动飞书机器人...")
        
        # 保存主事件循环引用
        self._main_loop = asyncio.get_event_loop()
        
        self._client = self._create_ws_client()
        self._stop_event.clear()
        
        try:
            # 在单独线程中启动客户端（因为 start() 是阻塞的）
            self._thread = threading.Thread(target=self._run_client, daemon=True)
            self._thread.start()
            
            # 等待连接建立
            await asyncio.sleep(2)
            
            self._connected = True
            logger.info("✅ 飞书机器人已启动，正在监听消息...")
            logger.info("💡 提示：请在飞书中给机器人发送任意消息以建立会话")
            
        except Exception as e:
            logger.error(f"启动飞书机器人失败: {e}")
            raise
    
    async def send_startup_message(self, message: str) -> bool:
        """
        发送启动问候消息
        
        Args:
            message: 问候消息内容
            
        Returns:
            是否发送成功
        """
        if not self._chat_id:
            logger.warning("无法发送启动问候：未获取到 chat_id，等待用户先发送消息")
            return False
        
        logger.info("发送启动问候消息...")
        return await self.send_text(message)
    
    async def stop(self) -> None:
        """停止 WebSocket 连接"""
        if self._thread and self._thread.is_alive():
            logger.info("正在关闭飞书机器人...")
            
            self._stop_event.set()
            self._connected = False
            
            # 给线程一些时间处理
            self._thread.join(timeout=3)
            
            logger.info("飞书机器人已关闭")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._thread and self._thread.is_alive()
    
    def get_chat_id(self) -> Optional[str]:
        """获取当前 chat_id"""
        return self._chat_id
