"""/update 指令处理器"""

from src.models import UserSession
from src.utils.formatter import format_scan_result
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.update")


class UpdateHandler(CommandHandler):
    """更新数据库指令"""

    @property
    def command(self) -> str:
        return "update"

    def get_usage(self) -> str:
        return "/update - 手动更新数据库"

    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /update 指令"""
        if not self.check_dependencies():
            return "服务未初始化，请稍后重试"

        logger.info("执行 /update 指令")

        deep_update = False
        if args:
            if args[0] == "深度":
                deep_update = True

        try:
            # 执行扫描
            result = await self._scanner.scan(
                deep_update=deep_update,
                notify_diff=False,
                notify_enrolled_change=True,
                notify_new_activities=True,
                notify_new_activities_with_ai_filter=True,
            )

            if result["success"]:
                return format_scan_result(result)
            else:
                error = result.get("error", "未知错误")
                return f"❌ 更新失败：{error}"

        except Exception as e:
            logger.error(f"更新失败: {e}")
            return f"❌ 更新失败：{str(e)}"
