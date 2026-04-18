"""/help 指令处理器"""

from src.notifications import Response
from src.utils.logger import get_logger

from .base import CommandHandler

logger = get_logger("feishu.handler.help")


class HelpHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "help"

    def get_usage(self) -> str:
        return "/help - 显示帮助信息"

    async def handle(self, args: list[str], session) -> Response:
        logger.info("执行 /help 指令")

        help_text = (
            "帮助信息\n\n"
            "/help 显示帮助信息\n"
            "\n\n"
            "/check [深度] [推送] [对比差异] 更新数据库并检查差异\n"
            "  深度 - 深度更新活动信息\n"
            "  推送 - 推送新活动和报名变化\n"
            "  对比差异 - 推送详细差异对比\n"
            "\n\n"
            "/valid [重新扫描] [全部] [深度] [重新筛选] 查看可报名活动\n"
            "  重新扫描 - 先更新数据库再查询\n"
            "  全部 - 显示所有活动（不进行筛选）\n"
            "  深度 - 深度更新活动信息\n"
            "  重新筛选 - 重新进行AI筛选\n"
            "\n\n"
            "/info [全部/其余] 查看已报名信息\n"
            "  全部 - 显示除结项外的所有活动\n"
            "  其余 - 显示公示/学时申请相关活动\n"
            "\n\n"
            "/cancel <序号> 取消报名\n"
            "\n\n"
            "/search <关键词> 搜索二课\n"
            "\n\n"
            "/join <序号> 报名二课\n"
            "\n\n"
            "/ignore <序号/全部/AI> 将活动加入不感兴趣列表\n"
            "  序号 - 将指定序号的活动加入不感兴趣列表，序号格式: 1,2,3 或 1-5\n"
            "  全部 - 将所有显示的活动加入不感兴趣列表\n"
            "  AI - 添加AI筛选掉的所有活动到不感兴趣列表\n"
            "  注：目前已加入一键不感兴趣按钮，点击即可将活动加入不感兴趣列表，一般情况下，无需该指令\n"
            "\n\n"
            "/interested <筛选类型> <序号> 将被筛选的活动标记为感兴趣\n"
            "  筛选类型: ai, 时间, 忽略/数据库\n"
            "  序号格式: 1,2,3 或 1-5 或 全部\n"
            "\n\n"
            "/alive 查看系统状态\n"
            "\n\n"
            "/menu 查看功能菜单\n"
            "\n\n"
            "/preference [感兴趣/不感兴趣] 查看已标记的活动列表\n"
            "  无参数 - 查看全部标记列表\n"
            "  感兴趣 - 只看感兴趣的活动\n"
            "  不感兴趣 - 只看不感兴趣的活动\n"
            "\n\n"
            "/upgrade 检查并安装程序更新\n"
            "  自动从 git 拉取最新代码并重启应用\n"
            "  如有更新会显示变更内容并要求确认\n"
        )
        return Response.text(help_text)
