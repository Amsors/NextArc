"""/check 指令处理器"""

from src.notifications import Response
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

    async def handle(self, args: list[str], session) -> Response:
        """处理 /check 指令"""
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        logger.info("执行 /check 指令")

        deep_update = False
        notify_diff = False
        notify_new_activities = False
        notify_enrolled_change = False
        no_filter = False

        if args:
            if "深度" in args:
                deep_update = True
            if "推送" in args:
                notify_new_activities = True
                notify_enrolled_change = True
            if "对比差异" in args:
                notify_diff = True
            if "全部" in args or "所有" in args:
                notify_new_activities = True

        try:
            result = await self._scanner.scan(
                deep_update=deep_update,
                notify_diff=notify_diff,
                notify_enrolled_change=notify_enrolled_change,
                notify_new_activities=notify_new_activities,
                no_filter=no_filter,
            )

            if result["success"]:
                lines = [format_scan_result(result)]

                # 添加差异详情
                diff = result.get("diff")
                if not diff or not diff.has_changes():
                    lines.append("")
                    lines.append("与上次扫描相比无变化")

                return Response.text("\n".join(lines))
            else:
                error = result.get("error", "未知错误")
                return Response.error(error, context="检查更新")

        except Exception as e:
            logger.error(f"检查失败: {e}")
            return Response.error(str(e), context="检查更新")
