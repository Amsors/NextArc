"""/search 指令处理器"""
import traceback

from pyustc.young import SecondClass

from src.feishu_bot.card_builder import CardButtonConfig
from src.models import UserSession
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.search")


class SearchHandler(CommandHandler):
    @property
    def command(self) -> str:
        return "search"

    def get_usage(self) -> str:
        return "/search <关键词> - 搜索活动关键词"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n示例：/search 讲座")

        keyword = " ".join(args)
        logger.info(f"执行 /search 指令，关键词: {keyword}")

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("暂无数据，请先执行 /update")
        if not self._activity_query_service:
            return Response.text("活动查询服务未初始化，请稍后重试")

        try:
            activities = await self._search_activities(latest_db, keyword)

            if not activities:
                return Response.text(f'搜索「{keyword}」\n\n未找到匹配的活动，请尝试其他关键词')

            try:
                update_service = self._activity_update_service
                if update_service is None:
                    return Response.text("活动更新服务未初始化，请稍后重试")

                update_result = await update_service.update_activities(
                    activities,
                    continue_on_error=True,
                )
                if update_result.failed:
                    hint = "部分活动信息可能不是最新"
                else:
                    hint = "活动已经更新，最新报名人数已显示"
            except Exception as e:
                logger.error(f"更新活动信息失败: {e}")
                hint = "部分活动信息可能不是最新"

            await session.context_manager.set_search_result(keyword, activities)
            await session.context_manager.set_displayed_activities(
                activities=activities,
                source="search",
            )

            title = f'搜索「{keyword}」结果（共{len(activities)}个）'
            if hint:
                title += f"\n{hint}"

            button_config = CardButtonConfig(
                show_ignore_button=True,
                show_interested_button=True,
                show_join_button=True,
                show_children_button=True
            )
            
            return Response.activity_list(
                activities,
                title=title,
                button_config=button_config
            )

        except Exception as e:
            logger.error(f"搜索活动失败: {e}")
            traceback.print_exc()
            return Response.error(str(e), context="搜索活动")

    async def _search_activities(self, db_path, keyword: str) -> list[SecondClass]:
        activities = await self._activity_query_service.search_activities(db_path, keyword)

        logger.debug(f"搜索结果: {len(activities)} 个活动")
        return activities
