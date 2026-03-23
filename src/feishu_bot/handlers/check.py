"""/check 指令处理器"""

from src.models import UserSession
from src.utils.formatter import format_scan_result
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.check")


class CheckHandler(CommandHandler):
    """检查差异指令"""

    @property
    def command(self) -> str:
        return "check"

    def get_usage(self) -> str:
        return "/check - 更新数据库并显示差异"

    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /check 指令"""
        if not self.check_dependencies():
            return "服务未初始化，请稍后重试"

        logger.info("执行 /check 指令")

        deep_update = False
        notify_new_activities = False
        notify_enrolled_change = False

        if args:
            if "深度" in args:
                deep_update = True
            elif "推送" in args:
                notify_new_activities = True
                notify_enrolled_change = True

        try:
            result = await self._scanner.scan(
                deep_update=deep_update,
                notify_diff=False,
                notify_enrolled_change=notify_enrolled_change,
                notify_new_activities=notify_new_activities,
                notify_new_activities_with_ai_filter=False,
            )

            if result["success"]:
                lines = [format_scan_result(result)]

                # 添加差异详情
                diff = result.get("diff")
                if diff and diff.has_changes():
                    lines.append("")
                    lines.append(diff.format_full())
                else:
                    lines.append("")
                    lines.append("✅ 与上次扫描相比无变化")

                return "\n".join(lines)
            else:
                error = result.get("error", "未知错误")
                return f"❌ 检查失败：{error}"

        except Exception as e:
            logger.error(f"检查失败: {e}")
            return f"❌ 检查失败：{str(e)}"
