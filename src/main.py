import asyncio
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 更新标记文件名
UPDATE_MARKER_FILE = ".next_arc_updated"

from src.config import load_settings
from src.config.preferences import load_preferences
from src.core import AuthManager, DatabaseManager, ActivityScanner, AIFilterConfig
from src.core.events import EventBus
from src.core.time_filter import TimeFilter
from src.core.user_preference_manager import UserPreferenceManager
from src.feishu_bot import FeishuBot, CardActionHandler
from src.feishu_bot.handlers.alive import AliveHandler
from src.feishu_bot.handlers.ignore import IgnoreHandler
from src.feishu_bot.handlers.valid import ValidHandler
from src.feishu_bot.message_router import MessageRouter
from src.notifications import (
    FeishuNotificationService,
    NotificationListener,
)
from src.utils import setup_logging, get_logger
from src.utils.formatter import format_scan_result

from pyustc.young import SecondClass

logger = get_logger("main")


class NextArcApp:
    """NextArc 应用主类"""

    def __init__(self):
        self.settings = None
        self.preferences = None
        self.event_bus: EventBus = None
        self.auth_manager: AuthManager = None
        self.db_manager: DatabaseManager = None
        self.user_preference_manager: UserPreferenceManager = None
        self.notification_service: FeishuNotificationService = None
        self.notification_listener: NotificationListener = None
        self.scanner: ActivityScanner = None
        self.bot: FeishuBot = None
        self.router: MessageRouter = None
        self.time_filter: TimeFilter = None
        self.card_handler: CardActionHandler = None
        self.version_checker = None
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
            setup_logging(
                level=self.settings.logging.level,
                file_enabled=self.settings.logging.file.enabled,
                file_path=self.settings.logging.file.path if self.settings.logging.file.enabled else None,
                max_size_mb=self.settings.logging.file.max_size_mb,
                backup_count=self.settings.logging.file.backup_count,
            )
            logger.info("=" * 60)
            logger.info("NextArc 启动中...")
            logger.info("=" * 60)
            logger.info(f"日志级别: {self.settings.logging.level}")
            if self.settings.logging.file.enabled:
                logger.info(f"文件日志: {self.settings.logging.file.path}")
                logger.info(f"   最大大小: {self.settings.logging.file.max_size_mb}MB")
                logger.info(f"   历史文件数: {self.settings.logging.file.backup_count}")

            # 检查当前 Python 环境
            self._check_environment()

            # 初始化数据库管理器
            self.db_manager = DatabaseManager(
                data_dir=self.settings.database.data_dir,
                max_history=self.settings.database.max_history,
            )
            logger.info(f"数据库管理器初始化完成，数据目录: {self.settings.database.data_dir}")

            # 初始化用户偏好管理器
            preference_db_path = self.settings.database.get_preference_db_path()
            self.user_preference_manager = UserPreferenceManager(
                db_path=preference_db_path
            )
            await self.user_preference_manager.initialize()
            ignored_count = await self.user_preference_manager.get_ignored_count()
            interested_count = await self.user_preference_manager.get_interested_count()
            logger.info(f"用户偏好管理器初始化完成")
            logger.info(f"   不感兴趣活动: {ignored_count} 个")
            logger.info(f"   感兴趣活动: {interested_count} 个")

            # 初始化事件总线
            self.event_bus = EventBus()
            logger.info("事件总线初始化完成")

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
                    logger.info(f"AI 筛选器初始化完成，模型: {self.settings.ai.model}")
                except (ValueError, FileNotFoundError) as e:
                    logger.error(f"AI 功能初始化失败: {e}")
                    logger.error("请检查 config.yaml 中的 AI 配置和提示词文件")
                    raise RuntimeError(f"AI 功能初始化失败: {e}") from e
            else:
                logger.info("AI 筛选: 已禁用")

            # 初始化版本检查器（如果启用）
            self.version_checker = None
            logger.info(f"版本检查配置: enabled={self.settings.version_check.enabled}")
            if self.settings.version_check.enabled:
                from src.core.version_checker import VersionChecker
                logger.info("正在初始化版本检查器...")
                logger.info(f"   配置: day_of_week={self.settings.version_check.day_of_week}, "
                            f"hour={self.settings.version_check.hour}, "
                            f"minute={self.settings.version_check.minute}")
                logger.info(f"   远程: {self.settings.version_check.remote_name}/"
                            f"{self.settings.version_check.branch_name}, "
                            f"auto_fetch={self.settings.version_check.auto_fetch}")

                self.version_checker = VersionChecker(
                    config=self.settings.version_check,
                    project_root=project_root,
                )
                # 验证 git 仓库
                if not self.version_checker.is_git_repo():
                    logger.warning("版本检查已启用，但当前目录不是 git 仓库")
                    self.version_checker = None
                else:
                    logger.info("版本检查器: 检测到 git 仓库")
                    current_ver = await self.version_checker.get_current_version()
                    remote_url = await self.version_checker.get_remote_url()
                    logger.info(f"版本检查器初始化完成")
                    logger.info(f"   远程仓库: {remote_url or 'unknown'}")
                    logger.info(f"   当前版本: {current_ver[:7] if current_ver else 'unknown'}")
            else:
                logger.info("版本检查: 已禁用")

            # 初始化时间筛选器（如果启用）
            self.time_filter = None
            use_time_filter = False
            if self.preferences and self.preferences.time_filter.enabled:
                if self.preferences.time_filter.weekly_preferences.has_any_preference():
                    self.time_filter = TimeFilter(self.preferences)
                    use_time_filter = True
                    logger.info("时间筛选器初始化完成")
                    logger.info(f"   重叠模式: {self.preferences.time_filter.get_overlap_mode_display()}")
                    logger.info("时间筛选配置:")
                    for line in self.preferences.time_filter.weekly_preferences.format_preferences().split("\n"):
                        if line.strip():  # 只显示非空行
                            logger.info(f"   {line}")
                else:
                    logger.warning("时间筛选已启用但未配置任何时间段，请在 config/preferences.yaml 中配置")
            else:
                logger.info("时间筛选: 已禁用")

            # 初始化扫描器
            self.scanner = ActivityScanner(
                auth_manager=self.auth_manager,
                db_manager=self.db_manager,
                event_bus=self.event_bus,
                interval_minutes=self.settings.monitor.interval_minutes,
                notify_new_activities=self.settings.monitor.notify_new_activities,
                ai_filter=ai_filter,
                use_ai_filter=self.settings.monitor.use_ai_filter and self.settings.ai.enabled,
                ai_user_info=self.settings.ai.user_info,
                time_filter=self.time_filter,
                use_time_filter=use_time_filter,
                user_preference_manager=self.user_preference_manager,
                version_checker=self.version_checker,
            )
            logger.info(f"扫描器初始化完成，间隔: {self.settings.monitor.interval_minutes}分钟")
            logger.info(f"新活动通知: {'开启' if self.settings.monitor.notify_new_activities else '关闭'}")
            if self.settings.monitor.use_ai_filter and self.settings.ai.enabled and ai_filter:
                logger.info(f"AI 筛选: 开启，模型: {self.settings.ai.model}")
            if use_time_filter and self.time_filter:
                logger.info("时间筛选: 开启")
            logger.info("数据库筛选: 已启用")

            # 初始化消息路由器
            self.router = MessageRouter()
            self.router.set_dependencies(self.scanner, self.auth_manager, self.db_manager, self.user_preference_manager)
            logger.info("消息路由器初始化完成")

            # 为 ValidHandler、AliveHandler、IgnoreHandler 和 InterestedHandler 设置偏好管理器
            from src.feishu_bot.handlers.interested import InterestedHandler
            ValidHandler.set_ignore_manager(self.user_preference_manager)
            AliveHandler.set_ignore_manager(self.user_preference_manager)
            IgnoreHandler.set_ignore_manager(self.user_preference_manager)
            InterestedHandler.set_user_preference_manager(self.user_preference_manager)

            # 初始化卡片交互处理器
            self.card_handler = CardActionHandler()
            self.card_handler.set_dependencies(
                user_preference_manager=self.user_preference_manager,
                auth_manager=self.auth_manager,
                bot=None  # 暂时为None，等bot创建后再设置
            )
            logger.info("卡片交互处理器初始化完成")

            # 初始化飞书机器人
            if self.settings.feishu.app_id and self.settings.feishu.app_secret:
                # 传入预配置的 chat_id（如果存在）
                chat_id = self.settings.feishu.chat_id if self.settings.feishu.chat_id else None
                self.bot = FeishuBot(
                    app_id=self.settings.feishu.app_id,
                    app_secret=self.settings.feishu.app_secret,
                    message_handler=self._handle_message,
                    chat_id=chat_id,
                    card_handler=self.card_handler,
                )

                # 更新 card_handler 中的 bot 引用
                self.card_handler.set_dependencies(
                    user_preference_manager=self.user_preference_manager,
                    auth_manager=self.auth_manager,
                    bot=self.bot
                )

                # 初始化通知服务
                self.notification_service = FeishuNotificationService(self.bot)
                logger.info("通知服务初始化完成")

                # 初始化通知监听器并订阅事件
                self.notification_listener = NotificationListener(
                    self.notification_service,
                    user_preference_manager=self.user_preference_manager
                )
                self.notification_listener.subscribe(self.event_bus)
                logger.info("通知监听器已订阅事件")

                # 设置 UserSession 引用，使定时扫描的新活动也能被 /ignore 忽略
                self.notification_listener.set_user_session(self.bot.user_session)
                logger.info("已设置 UserSession 引用到通知监听器")

                if chat_id:
                    logger.info(f"飞书机器人初始化完成（已配置 chat_id: {chat_id}）")
                else:
                    logger.info("飞书机器人初始化完成（未配置 chat_id，等待用户发送消息）")
            else:
                logger.warning("未配置飞书 App ID 和 Secret，机器人功能不可用")

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
            logger.warning("未检测到 conda 环境，建议激活 'pyustc' 环境运行")
        else:
            logger.info("检测到 conda 环境")

    async def _handle_message(self, text: str, session) -> str | None:
        """
        处理飞书消息

        Args:
            text: 消息文本
            session: 用户会话

        Returns:
            如果返回字符串，则会发送该文本；如果返回 None，则表示消息已通过通知服务发送
        """
        response = await self.router.handle_message(text, session)

        # 通过通知服务发送响应
        if self.notification_service:
            await self.notification_service.send_response(response)
            return None  # 已通过通知服务发送，不需要再返回文本

        # 如果没有通知服务，返回文本内容（后适兼）
        if response.type.value == "text":
            return response.content
        return None

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

                # 检查是否是更新后重启，如果是则发送更新通知
                await self._check_and_notify_update()

                # 发送启动问候消息
                startup_msg = self._get_startup_message()
                # 尝试发送（如果已知 chat_id）
                success = await self.bot.send_startup_message(startup_msg)
                if not success:
                    logger.info("请在飞书中给机器人发送任意消息以激活会话")

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
            "NextArc 已启动！",
            "",
        ]

        # 显示当前启用的筛选功能
        filter_details = []
        if self.settings and self.settings.monitor.use_ai_filter and self.settings.ai.enabled:
            filter_details.append("AI筛选")
        if self.time_filter and self.time_filter.is_enabled():
            overlap_mode = self.preferences.time_filter.overlap_mode
            if overlap_mode == "partial":
                mode_desc = "有重叠即过滤"
            else:
                mode_desc = "完全包含才过滤"
            filter_details.append(f"时间筛选({mode_desc})")
        # 数据库筛选始终启用
        filter_details.append("数据库筛选(不感兴趣)")

        if filter_details:
            lines.append("已启用筛选：")
            for detail in filter_details:
                lines.append(f"  {detail}")
            lines.append("")

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
            "ignore_count": self.user_preference_manager.get_ignored_count_sync() if self.user_preference_manager else 0,
            "interested_count": self.user_preference_manager.get_interested_count_sync() if self.user_preference_manager else 0,
        }

    def _get_update_marker_path(self) -> Path:
        """获取更新标记文件路径"""
        return project_root / UPDATE_MARKER_FILE

    def _has_update_marker(self) -> bool:
        """检查是否存在更新标记文件"""
        marker_path = self._get_update_marker_path()
        return marker_path.exists()

    def _remove_update_marker(self) -> bool:
        """删除更新标记文件"""
        try:
            marker_path = self._get_update_marker_path()
            if marker_path.exists():
                marker_path.unlink()
                logger.info(f"已删除更新标记文件: {marker_path}")
                return True
        except Exception as e:
            logger.error(f"删除更新标记文件失败: {e}")
        return False

    async def _check_and_notify_update(self):
        """检查更新标记并发送更新通知"""
        if not self._has_update_marker():
            return

        logger.info("检测到更新标记文件，发送更新通知...")

        if self.bot and self.bot.is_connected():
            try:
                success = await self.bot.send_text("NextArc 已完成自更新")
                if success:
                    logger.info("已发送更新通知消息")
                else:
                    logger.warning("发送更新通知消息失败")
            except Exception as e:
                logger.error(f"发送更新通知消息异常: {e}")
        else:
            logger.warning("飞书机器人未连接，无法发送更新通知")

        self._remove_update_marker()


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
