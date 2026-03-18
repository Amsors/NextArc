"""/search 指令处理器"""

import aiosqlite

from src.models import UserSession
from src.models.activity import Activity
from src.utils.formatter import format_search_results
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
    
    async def handle(self, args: list[str], session: UserSession) -> str:
        """处理 /search 指令"""
        if not self.check_dependencies():
            return "服务未初始化，请稍后重试"
        
        # 检查参数
        if not args:
            return f"用法：{self.get_usage()}\n\n示例：/search 讲座"
        
        keyword = " ".join(args)
        logger.info(f"执行 /search 指令，关键词: {keyword}")
        
        # 获取最新数据库
        latest_db = self._db_manager.get_latest_db()
        if not latest_db:
            return "❌ 暂无数据，请先执行 /update"
        
        try:
            # 搜索活动
            activities = await self._search_activities(latest_db, keyword)
            
            if not activities:
                return f'🔍 搜索「{keyword}」\n\n未找到匹配的活动，请尝试其他关键词'
            
            # 保存搜索上下文
            session.set_search(keyword, activities)
            
            return format_search_results(activities, keyword)
            
        except Exception as e:
            logger.error(f"搜索活动失败: {e}")
            return f"❌ 搜索失败：{str(e)}"
    
    async def _search_activities(self, db_path, keyword: str) -> list[Activity]:
        """从数据库搜索活动"""
        activities = []
        keyword_lower = keyword.lower()
        
        logger.debug(f"搜索关键词: {keyword_lower}")
        
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            # 使用 LIKE 进行模糊搜索
            async with conn.execute(
                "SELECT * FROM all_secondclass WHERE LOWER(name) LIKE ? ORDER BY name",
                (f"%{keyword_lower}%",)
            ) as cursor:
                async for row in cursor:
                    activities.append(Activity.from_db_row(dict(row)))
        
        logger.debug(f"搜索结果: {len(activities)} 个活动")
        
        # 如果没有结果，记录一些调试信息
        if not activities:
            async with aiosqlite.connect(db_path) as conn:
                async with conn.execute("SELECT COUNT(*) FROM all_secondclass") as cursor:
                    total = (await cursor.fetchone())[0]
                    logger.debug(f"数据库中共有 {total} 个活动")
                
                # 列出几个活动名称供参考
                async with conn.execute(
                    "SELECT name FROM all_secondclass LIMIT 5"
                ) as cursor:
                    sample = [row[0] for row in await cursor.fetchall()]
                    logger.debug(f"示例活动: {sample}")
        
        return activities
