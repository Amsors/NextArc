import asyncio
import re
import signal
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

UPDATE_MARKER_FILE = ".next_arc_updated"
VERSION_FILE_NAME = ".next_arc_version"
CHANGE_LOG_FILE = "docs/change_log.md"

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
        self._should_notify_file_auth_deprecation = False
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> bool:
        try:
            self.settings = load_settings()
            self._should_notify_file_auth_deprecation = self.settings.is_using_file_credentials()

            preferences_path = project_root / "config" / "preferences.yaml"
            self.preferences = load_preferences(preferences_path)

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

            self._check_environment()

            self.db_manager = DatabaseManager(
                data_dir=self.settings.database.data_dir,
                max_history=self.settings.database.max_history,
            )
            logger.info(f"数据库管理器初始化完成，数据目录: {self.settings.database.data_dir}")

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

            self.event_bus = EventBus()
            logger.info("事件总线初始化完成")

            username, password = self.settings.get_credentials()
            self.auth_manager = AuthManager(username, password)
            logger.info(f"认证管理器初始化完成，认证方式: {self.settings.ustc.auth_mode}")

            logger.info("正在测试登录...")
            max_login_retries = 5
            for attempt in range(1, max_login_retries + 1):
                try:
                    async with self.auth_manager.create_session_once() as service:
                        depts = await SecondClass.get_departments()
                        logger.info(f"登录测试成功，获取到 {len(depts)} 个根部门")
                        break
                except Exception as e:
                    logger.warning(f"登录测试失败 (尝试 {attempt}/{max_login_retries}): {e}")
                    if attempt == max_login_retries:
                        raise
                    await asyncio.sleep(5)

            ai_filter = None
            if self.settings.monitor.use_ai_filter and self.settings.ai.enabled:
                try:
                    ai_filter = AIFilterConfig.create_from_settings(self.settings)
                    logger.info(f"AI 筛选器初始化完成，模型: {self.settings.ai.model}")

                    logger.info("正在测试 AI API 连接...")
                    try:
                        success, message = await ai_filter.test_connection()
                        if success:
                            logger.info(f"AI API 测试: {message}")
                        else:
                            logger.error(f"AI API 测试: {message}")
                    except Exception as e:
                        logger.error(f"AI API 测试失败: {e}")

                except (ValueError, FileNotFoundError) as e:
                    logger.error(f"AI 功能初始化失败: {e}")
                    logger.error("请检查 config.yaml 中的 AI 配置和提示词文件")
                    raise RuntimeError(f"AI 功能初始化失败: {e}") from e
            else:
                logger.info("AI 筛选: 已禁用")

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
                        if line.strip():
                            logger.info(f"   {line}")
                else:
                    logger.warning("时间筛选已启用但未配置任何时间段，请在 config/preferences.yaml 中配置")
            else:
                logger.info("时间筛选: 已禁用")

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

            self.router = MessageRouter()
            self.router.set_dependencies(self.scanner, self.auth_manager, self.db_manager, self.user_preference_manager)
            logger.info("消息路由器初始化完成")

            from src.feishu_bot.handlers.interested import InterestedHandler
            ValidHandler.set_ignore_manager(self.user_preference_manager)
            AliveHandler.set_ignore_manager(self.user_preference_manager)
            IgnoreHandler.set_ignore_manager(self.user_preference_manager)
            InterestedHandler.set_user_preference_manager(self.user_preference_manager)

            self.card_handler = CardActionHandler()
            self.card_handler.set_dependencies(
                user_preference_manager=self.user_preference_manager,
                auth_manager=self.auth_manager,
                bot=None  # 暂时为None，等bot创建后再设置
            )
            logger.info("卡片交互处理器初始化完成")

            if self.settings.feishu.app_id and self.settings.feishu.app_secret:
                chat_id = self.settings.feishu.chat_id if self.settings.feishu.chat_id else None
                self.bot = FeishuBot(
                    app_id=self.settings.feishu.app_id,
                    app_secret=self.settings.feishu.app_secret,
                    message_handler=self._handle_message,
                    chat_id=chat_id,
                    card_handler=self.card_handler,
                )

                self.card_handler.set_dependencies(
                    user_preference_manager=self.user_preference_manager,
                    auth_manager=self.auth_manager,
                    bot=self.bot
                )

                self.notification_service = FeishuNotificationService(self.bot)
                logger.info("通知服务初始化完成")

                self.notification_listener = NotificationListener(
                    self.notification_service,
                    user_preference_manager=self.user_preference_manager
                )
                self.notification_listener.subscribe(self.event_bus)
                logger.info("通知监听器已订阅事件")

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
        import sys

        exe = sys.executable
        logger.info(f"Python 解释器: {exe}")

        if "conda" not in exe.lower() and "envs" not in exe:
            logger.warning("未检测到 conda 环境，建议激活 'pyustc' 环境运行")
        else:
            logger.info("检测到 conda 环境")

    async def _handle_message(self, text: str, session) -> str | None:
        response = await self.router.handle_message(text, session)

        if self.notification_service:
            await self.notification_service.send_response(response)
            return None  # 已通过通知服务发送，不需要再返回文本
        # TODO 重新检查此处逻辑

        # 如果没有通知服务，返回文本内容（后适兼）
        if response.type.value == "text":
            return response.content
        return None

    async def run(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        try:
            self.scanner.start()

            if self.settings.behavior.scan_on_start:
                logger.info("执行首次扫描...")
                max_scan_retries = 3
                for attempt in range(1, max_scan_retries + 1):
                    try:
                        result = await self.scanner.scan(
                            deep_update=True,
                            notify_diff=False,
                            notify_enrolled_change=False,
                            notify_new_activities=False,
                            no_filter=False,
                        )
                        logger.info(format_scan_result(result))
                        break
                    except Exception as e:
                        logger.warning(f"首次扫描失败 (尝试 {attempt}/{max_scan_retries}): {e}")
                        if attempt == max_scan_retries:
                            raise
                        await asyncio.sleep(5)
            else:
                logger.info("首次扫描已禁用，将在下次定时扫描时执行")

            if self.bot:
                await self.bot.start()

                await self._check_and_notify_update()
                await self._notify_file_auth_deprecation()

                startup_msg = self._get_startup_message()
                success = await self.bot.send_startup_message(startup_msg)
                if not success:
                    logger.info("请在飞书中给机器人发送任意消息以激活会话")

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
        lines = [
            "NextArc 已启动！",
            "",
        ]

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
        filter_details.append("数据库筛选(不感兴趣)")

        if filter_details:
            lines.append("已启用筛选：")
            for detail in filter_details:
                lines.append(f"  {detail}")
            lines.append("")

        return "\n".join(lines)

    def _signal_handler(self) -> None:
        logger.info("收到关闭信号...")
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        logger.info("正在关闭应用...")

        if self.scanner:
            self.scanner.stop()

        if self.bot:
            await self.bot.stop()

        logger.info("应用已关闭")

    def get_status(self) -> dict:
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
        return project_root / UPDATE_MARKER_FILE

    def _has_update_marker(self) -> bool:
        marker_path = self._get_update_marker_path()
        return marker_path.exists()

    def _read_update_marker_version(self) -> str | None:
        marker_path = self._get_update_marker_path()

        try:
            if not marker_path.exists():
                return None

            content = marker_path.read_text(encoding="utf-8").strip()
            if not content:
                return None

            if not re.fullmatch(r"\d+\.\d+\.\d+", content):
                logger.warning(f"更新标记文件中的版本号格式无效: {content}")
                return None

            return content
        except Exception as e:
            logger.error(f"读取更新标记文件失败: {e}")
            return None

    def _remove_update_marker(self) -> bool:
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

        await self._notify_change_logs_since_last_version()
        self._remove_update_marker()

    def _get_current_semantic_version(self) -> str | None:
        version_file = project_root / VERSION_FILE_NAME

        try:
            if not version_file.exists():
                logger.warning(f"版本文件不存在: {version_file}")
                return None

            version = version_file.read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                logger.warning(f"版本号格式无效: {version}")
                return None

            return version
        except Exception as e:
            logger.error(f"读取版本文件失败: {e}")
            return None

    def _parse_semantic_version(self, version: str) -> tuple[int, int, int] | None:
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            return None

        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

    def _get_change_log_sections(self) -> list[tuple[str, str]]:
        change_log_path = project_root / CHANGE_LOG_FILE

        try:
            if not change_log_path.exists():
                logger.warning(f"更新日志文件不存在: {change_log_path}")
                return []

            content = change_log_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"读取更新日志失败: {e}")
            return []

        lines = content.splitlines()
        sections: list[tuple[str, str]] = []
        current_version: str | None = None
        current_start_index: int | None = None

        def flush_section(end_index: int) -> None:
            nonlocal current_version, current_start_index
            if current_version is None or current_start_index is None:
                return

            section = "\n".join(lines[current_start_index:end_index]).strip()
            if section:
                sections.append((current_version, section))

        for index, line in enumerate(lines):
            match = re.fullmatch(r"## v(\d+\.\d+\.\d+)\s*", line.strip())
            if match:
                flush_section(index)
                current_version = match.group(1)
                current_start_index = index

        flush_section(len(lines))
        return sections

    async def _notify_change_logs_since_last_version(self):
        if not self.bot or not self.bot.is_connected():
            logger.warning("飞书机器人未连接，无法发送更新说明")
            return

        current_version = self._get_current_semantic_version()
        if not current_version:
            return

        previous_version = self._read_update_marker_version()
        sections = self._get_change_log_sections()
        if not sections:
            return

        current_semver = self._parse_semantic_version(current_version)
        if not current_semver:
            logger.warning("无法解析当前版本号，跳过更新说明发送")
            return

        if not previous_version:
            logger.warning("更新标记文件中未记录有效旧版本，按老版本升级处理，发送全部更新说明")
            pending_sections = sections
        else:
            previous_semver = self._parse_semantic_version(previous_version)
            if not previous_semver:
                logger.warning("无法解析旧版本号，按老版本升级处理，发送全部更新说明")
                pending_sections = sections
            else:
                pending_sections = [
                    (version, section)
                    for version, section in sections
                    if previous_semver < self._parse_semantic_version(version) <= current_semver
                ]

        if not pending_sections:
            logger.info(f"未找到从 v{previous_version} 到 v{current_version} 之间的更新说明")
            return

        pending_sections.sort(key=lambda item: self._parse_semantic_version(item[0]))

        for version, section in pending_sections:
            message = (f"更新说明（v{version}）\n"
                       f"提示：建议前往 Github 查看渲染好 Markdown 的更新日志\n"
                       f"\n{section}")

            try:
                success = await self.bot.send_text(message)
                if success:
                    logger.info(f"已发送版本 v{version} 的更新说明")
                else:
                    logger.warning(f"发送版本 v{version} 的更新说明失败")
            except Exception as e:
                logger.error(f"发送版本 v{version} 的更新说明异常: {e}")

    async def _notify_file_auth_deprecation(self):
        if not self._should_notify_file_auth_deprecation:
            return

        logger.warning("检测到 USTC 账号密码仍通过 config.yaml 明文读取，建议迁移到环境变量")

        if not self.bot or not self.bot.is_connected():
            logger.warning("飞书机器人未连接，无法发送文件凭据安全提醒")
            return

        message = (
            "❗❗❗❗❗\n"
            "安全提醒：当前账号密码仍通过 config.yaml 明文读取。\n"
            "这会增加凭据被其他软件或误操作读取的风险，建议尽快迁移到环境变量模式。\n"
            "推荐配置：ustc.auth_mode: \"env\"\n"
            "环境变量：USTC_USERNAME、USTC_PASSWORD\n\n"
            "为了安全性，后续版本将强制要求从环境变量中读取账号密码！"
        )

        try:
            success = await self.bot.send_text(message)
            if success:
                logger.info("已发送文件凭据安全提醒")
            else:
                logger.warning("发送文件凭据安全提醒失败")
        except Exception as e:
            logger.error(f"发送文件凭据安全提醒异常: {e}")


async def main():
    print("=" * 60)
    print("NextArc - 第二课堂活动监控机器人")
    print("=" * 60)
    print()

    if sys.version_info < (3, 10):
        print("错误：需要 Python 3.10 或更高版本")
        sys.exit(1)

    app = NextArcApp()

    if not await app.initialize():
        print("初始化失败，请检查配置")
        sys.exit(1)

    try:
        await app.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n程序已退出")


if __name__ == "__main__":
    asyncio.run(main())
