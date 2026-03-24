import asyncio
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_settings
from src.config.preferences import load_preferences
from src.core import AuthManager, DatabaseManager, ActivityScanner, AIFilterConfig
from src.core.ignore_manager import IgnoreManager
from src.core.time_filter import TimeFilter
from src.feishu_bot import FeishuBot
from src.feishu_bot.handlers.alive import AliveHandler
from src.feishu_bot.handlers.ignore import IgnoreHandler
from src.feishu_bot.handlers.valid import ValidHandler
from src.feishu_bot.message_router import MessageRouter
from src.utils import setup_logging, get_logger
from src.utils.formatter import format_scan_result

from pyustc.young import SecondClass

logger = get_logger("main")


class NextArcApp:
    """NextArc 应用主类"""

    def __init__(self):
        self.settings = None
        self.preferences = None
        self.auth_manager: AuthManager = None
        self.db_manager: DatabaseManager = None
        self.ignore_manager: IgnoreManager = None
        self.scanner: ActivityScanner = None
        self.bot: FeishuBot = None
        self.router: MessageRouter = None
        self.time_filter: TimeFilter = None
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> bool:
        """
        初始化应用
        
        Returns:
            是否初始化成功
        """
        try:
            # 加载主配置（从项目根目录的 config/ 目录加载）
            self.settings = load_settings()

            # 加载推送偏好配置
            preferences_path = project_root / "config" / "preferences.yaml"
            self.preferences = load_preferences(preferences_path)

            # 初始化日志
            setup_logging(self.settings.logging.level)
            logger.info("=" * 60)
            logger.info("NextArc 启动中...")
            logger.info("=" * 60)
            logger.info(f"日志级别: {self.settings.logging.level}")

            # 检查当前 Python 环境
            self._check_environment()

            # 初始化数据库管理器
            self.db_manager = DatabaseManager(
                data_dir=self.settings.database.data_dir,
                max_history=self.settings.database.max_history,
            )
            logger.info(f"数据库管理器初始化完成，数据目录: {self.settings.database.data_dir}")

            # 初始化忽略管理器
            self.ignore_manager = IgnoreManager(
                db_path=project_root / "data" / "ignore.db"
            )
            await self.ignore_manager.initialize()
            ignored_count = await self.ignore_manager.get_ignored_count()
            logger.info(f"✅ 忽略管理器初始化完成，已有 {ignored_count} 个被忽略的活动")

            # 获取凭据并初始化认证管理器
            username, password = self.settings.get_credentials()
            self.auth_manager = AuthManager(username, password)
            logger.info(f"认证管理器初始化完成，用户名: {username}")

            # 测试登录（使用 create_session_once）
            logger.info("正在测试登录...")
            async with self.auth_manager.create_session_once() as service:
                depts = await SecondClass.get_departments()
                logger.info(f"登录测试成功，获取到 {len(depts)} 个根部门")

            # 初始化 AI 筛选器（如果启用）
            ai_filter = None
            if self.settings.monitor.use_ai_filter and self.settings.ai.enabled:
                try:
                    ai_filter = AIFilterConfig.create_from_settings(self.settings)
                    logger.info(f"✅ AI 筛选器初始化完成，模型: {self.settings.ai.model}")
                except (ValueError, FileNotFoundError) as e:
                    logger.error(f"❌ AI 功能初始化失败: {e}")
                    logger.error("请检查 config.yaml 中的 AI 配置和提示词文件")
                    raise RuntimeError(f"AI 功能初始化失败: {e}") from e
            else:
                logger.info("AI 筛选: 已禁用")

            # 初始化时间筛选器（如果启用）
            self.time_filter = None
            use_time_filter = False
            if self.preferences and self.preferences.time_filter.enabled:
                if self.preferences.time_filter.weekly_preferences.has_any_preference():
                    self.time_filter = TimeFilter(self.preferences)
                    use_time_filter = True
                    logger.info("✅ 时间筛选器初始化完成")
                    logger.info(f"   重叠模式: {self.preferences.time_filter.get_overlap_mode_display()}")
                    logger.info("📅 时间筛选配置:")
                    for line in self.preferences.time_filter.weekly_preferences.format_preferences().split("\n"):
                        if line.strip():  # 只显示非空行
                            logger.info(f"   {line}")
                else:
                    logger.warning("⚠️ 时间筛选已启用但未配置任何时间段，请在 config/preferences.yaml 中配置")
            else:
                logger.info("时间筛选: 已禁用")

            # 初始化扫描器
            self.scanner = ActivityScanner(
                auth_manager=self.auth_manager,
                db_manager=self.db_manager,
                interval_minutes=self.settings.monitor.interval_minutes,
                notify_callback=self._on_notify,
                notify_new_activities=self.settings.monitor.notify_new_activities,
                ai_filter=ai_filter,
                use_ai_filter=self.settings.monitor.use_ai_filter and self.settings.ai.enabled,
                ai_user_info=self.settings.ai.user_info,
                time_filter=self.time_filter,
                use_time_filter=use_time_filter,
                card_notify_callback=self._on_card_notify,
                ignore_manager=self.ignore_manager,
            )
            logger.info(f"扫描器初始化完成，间隔: {self.settings.monitor.interval_minutes}分钟")
            logger.info(f"新活动通知: {'开启' if self.settings.monitor.notify_new_activities else '关闭'}")
            if self.settings.monitor.use_ai_filter and self.settings.ai.enabled and ai_filter:
                logger.info(f"AI 筛选: 开启，模型: {self.settings.ai.model}")
            if use_time_filter and self.time_filter:
                logger.info("时间筛选: 开启")
            logger.info("🗑️ 数据库筛选: 已启用")

            # 初始化消息路由器
            self.router = MessageRouter()
            self.router.set_dependencies(self.scanner, self.auth_manager, self.db_manager, self.ignore_manager)
            logger.info("消息路由器初始化完成")

            # 为 ValidHandler、AliveHandler 和 IgnoreHandler 设置忽略管理器
            ValidHandler.set_ignore_manager(self.ignore_manager)
            AliveHandler.set_ignore_manager(self.ignore_manager)
            IgnoreHandler.set_ignore_manager(self.ignore_manager)

            # 初始化飞书机器人
            if self.settings.feishu.app_id and self.settings.feishu.app_secret:
                # 传入预配置的 chat_id（如果存在）
                chat_id = self.settings.feishu.chat_id if self.settings.feishu.chat_id else None
                self.bot = FeishuBot(
                    app_id=self.settings.feishu.app_id,
                    app_secret=self.settings.feishu.app_secret,
                    message_handler=self._handle_message,
                    chat_id=chat_id,
                )
                # 设置卡片发送回调（用于 /valid 等指令发送折叠卡片）
                self.router.set_card_sender(self.bot.send_card)
                if chat_id:
                    logger.info(f"飞书机器人初始化完成（已配置 chat_id: {chat_id}）")
                else:
                    logger.info("飞书机器人初始化完成（未配置 chat_id，等待用户发送消息）")
            else:
                logger.warning("⚠️ 未配置飞书 App ID 和 Secret，机器人功能不可用")

            return True

        except Exception as e:
            logger.error(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _check_environment(self) -> None:
        """检查运行环境"""
        import sys

        exe = sys.executable
        logger.info(f"Python 解释器: {exe}")

        # 检查是否在 conda 环境中
        if "conda" not in exe.lower() and "envs" not in exe:
            logger.warning("⚠️ 未检测到 conda 环境，建议激活 'pyustc' 环境运行")
        else:
            logger.info("✅ 检测到 conda 环境")

    async def _handle_message(self, text: str, session) -> str:
        """
        处理飞书消息
        
        Args:
            text: 消息文本
            session: 用户会话
            
        Returns:
            回复消息
        """
        return await self.router.handle_message(text, session)

    async def _on_notify(self, message: str) -> None:
        """
        通知回调 - 通过飞书发送通知
        
        Args:
            message: 通知消息
        """
        if self.bot and self.bot.is_connected():
            await self.bot.send_text(message)
        else:
            logger.info(f"[通知] {message}")

    async def _on_card_notify(self, card_content: dict) -> None:
        """
        卡片通知回调 - 通过飞书发送卡片消息
        
        Args:
            card_content: 卡片内容字典
        """
        if self.bot and self.bot.is_connected():
            await self.bot.send_card(card_content)
        else:
            logger.info(f"[卡片通知] 无法发送卡片（bot未连接）")

    async def run(self) -> None:
        """运行应用"""
        # 注册信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        try:
            # 启动定时扫描
            self.scanner.start()

            # 执行首次扫描
            if self.settings.behavior.scan_on_start:
                logger.info("执行首次扫描...")
                result = await self.scanner.scan(
                    deep_update=True,
                    notify_diff=False,
                    notify_enrolled_change=False,
                    notify_new_activities=False,
                    no_filter=False,
                )
                logger.info(format_scan_result(result))
            else:
                logger.info("首次扫描已禁用，将在下次定时扫描时执行")

            # 启动飞书机器人（如果已配置）
            if self.bot:
                await self.bot.start()

                # 发送启动问候消息
                startup_msg = self._get_startup_message()
                # 尝试发送（如果已知 chat_id）
                success = await self.bot.send_startup_message(startup_msg)
                if not success:
                    logger.info("💡 提示：请在飞书中给机器人发送任意消息以激活会话")

            # 等待关闭信号
            logger.info("应用运行中，按 Ctrl+C 停止...")
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"运行时错误: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await self.shutdown()

    def _get_startup_message(self) -> str:
        """获取启动问候消息"""
        lines = [
            "🤖 NextArc 已启动！",
            "",
            "我是您的第二课堂活动监控助手。",
            "",
        ]

        # 显示当前启用的筛选功能
        filter_details = []
        if self.settings and self.settings.monitor.use_ai_filter and self.settings.ai.enabled:
            filter_details.append("🤖 AI筛选")
        if self.time_filter and self.time_filter.is_enabled():
            overlap_mode = self.preferences.time_filter.overlap_mode
            if overlap_mode == "partial":
                mode_desc = "有重叠即过滤"
            else:
                mode_desc = "完全包含才过滤"
            filter_details.append(f"⏰ 时间筛选({mode_desc})")
        # 数据库筛选始终启用
        filter_details.append("🗑️ 数据库筛选(不感兴趣)")

        if filter_details:
            lines.append("已启用筛选：")
            for detail in filter_details:
                lines.append(f"  {detail}")
            lines.append("")

        lines.extend([
            "可用指令：",
            "/alive - 检查服务状态",
            "/update - 手动更新数据库",
            "/check - 更新并显示差异",
            "/info - 查看已报名活动",
            "/search <关键词> - 搜索活动",
            "/join <序号> - 报名活动",
            "/cancel <序号> - 取消报名",
            "",
            "🗑️ 不感兴趣功能：",
            "发送「不感兴趣 序号」将活动加入忽略列表",
            "序号格式：1,2,3 或 1-5 或 全部",
            "",
            "💡 提示：搜索结果有效期5分钟，报名/取消需要二次确认。",
        ])

        return "\n".join(lines)

    def _signal_handler(self) -> None:
        """处理关闭信号"""
        logger.info("收到关闭信号...")
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        """关闭应用"""
        logger.info("正在关闭应用...")

        if self.scanner:
            self.scanner.stop()

        if self.bot:
            await self.bot.stop()

        logger.info("应用已关闭")

    def get_status(self) -> dict:
        """获取应用状态"""
        return {
            "is_running": self.scanner.is_running() if self.scanner else False,
            "last_scan": self.scanner.get_last_scan_time() if self.scanner else None,
            "next_scan": self.scanner.get_next_scan_time() if self.scanner else None,
            "is_logged_in": self.auth_manager.is_logged_in() if self.auth_manager else False,
            "db_count": self.db_manager.get_db_count() if self.db_manager else 0,
            "bot_connected": self.bot.is_connected() if self.bot else False,
            "time_filter_enabled": self.time_filter.is_enabled() if self.time_filter else False,
            "ignore_count": self.ignore_manager.get_ignored_count() if self.ignore_manager else 0,
        }


async def main():
    """主函数"""
    print("=" * 60)
    print("NextArc - 第二课堂活动监控机器人")
    print("=" * 60)
    print()

    # 检查 Python 版本
    if sys.version_info < (3, 10):
        print("错误：需要 Python 3.10 或更高版本")
        sys.exit(1)

    app = NextArcApp()

    # 初始化
    if not await app.initialize():
        print("初始化失败，请检查配置")
        sys.exit(1)
    else:
        print("初始化成功！")

    # 运行应用
    try:
        await app.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n感谢使用 NextArc!")


if __name__ == "__main__":
    asyncio.run(main())
