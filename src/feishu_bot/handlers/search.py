"""/search 指令处理器"""
import traceback

import aiosqlite
from pyustc.young import SecondClass

from src.models import UserSession, secondclass_from_db_row
from src.notifications import Response
from src.utils.logger import get_logger
from .base import CommandHandler

logger = get_logger("feishu.handler.search")


class SearchHandler(CommandHandler):
    """搜索活动指令"""

    @property
    def command(self) -> str:
        return "search"

    def get_usage(self) -> str:
        return "/search <关键词> - 搜索标题含关键词的活动"

    async def handle(self, args: list[str], session: UserSession) -> Response:
        """处理 /search 指令"""
        if not self.check_dependencies():
            return Response.text("服务未初始化，请稍后重试")

        if not args:
            return Response.text(f"用法：{self.get_usage()}\n\n示例：/search 讲座")

        keyword = " ".join(args)
        logger.info(f"执行 /search 指令，关键词: {keyword}")

        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return Response.text("暂无数据，请先执行 /update")

        try:
            activities = await self._search_activities(latest_db, keyword)

            if not activities:
                return Response.text(f'搜索「{keyword}」\n\n未找到匹配的活动，请尝试其他关键词')

            try:
                async with self._auth_manager.create_session_once() as service:
                    for activity in activities:
                        try:
                            await activity.update()
                            logger.debug(f"更新活动信息成功: {activity.name}")
                        except Exception as e:
                            logger.warning(f"更新活动 {activity.id} 信息失败: {e}")

                hint = "活动已经更新，最新报名人数已显示"
            except Exception as e:
                logger.error(f"更新活动信息失败: {e}")
                hint = "部分活动信息可能不是最新"

            session.set_search(keyword, activities)

            # 不显示"不感兴趣"按钮
            title = f'搜索「{keyword}」结果（共{len(activities)}个）'
            if hint:
                title += f"\n{hint}"
            return Response.activity_list(
                activities,
                title=title,
                show_ignore_button=False
            )

        except Exception as e:
            logger.error(f"搜索活动失败: {e}")
            traceback.print_exc()
            return Response.error(str(e), context="搜索活动")

    async def _search_activities(self, db_path, keyword: str) -> list[SecondClass]:
        """从数据库搜索活动"""
        activities = []
        keyword_lower = keyword.lower()

        logger.debug(f"搜索关键词: {keyword_lower}")

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                    "SELECT * FROM all_secondclass WHERE LOWER(name) LIKE ? ORDER BY name",
                    (f"%{keyword_lower}%",)
            ) as cursor:
                async for row in cursor:
                    activities.append(secondclass_from_db_row(dict(row)))

        logger.debug(f"搜索结果: {len(activities)} 个活动")

        if not activities:
            async with aiosqlite.connect(db_path) as conn:
                async with conn.execute("SELECT COUNT(*) FROM all_secondclass") as cursor:
                    total = (await cursor.fetchone())[0]
                    logger.debug(f"数据库中共有 {total} 个活动")

                async with conn.execute(
                        "SELECT name FROM all_secondclass LIMIT 5"
                ) as cursor:
                    sample = [row[0] for row in await cursor.fetchall()]
                    logger.debug(f"示例活动: {sample}")

        return activities
