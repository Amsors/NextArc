"""定时扫描器"""
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pyustc.young import SecondClass
from pyustc.young.db import SecondClassDB

from src.models import DiffResult, Activity, secondclass_to_activity
from src.utils.logger import get_logger

from .auth_manager import AuthManager
from .db_manager import DatabaseManager
from .diff_engine import DiffEngine

logger = get_logger("scanner")


class ActivityScanner:
    """
    定时扫描第二课堂活动
    - 使用 apscheduler 调度定时任务
    - 创建新的时间戳数据库
    - 对比差异并推送通知
    """
    
    def __init__(
        self,
        auth_manager: AuthManager,
        db_manager: DatabaseManager,
        interval_minutes: int = 15,
        notify_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
    ):
        self.auth_manager = auth_manager
        self.db_manager = db_manager
        self.interval = interval_minutes
        self.notify_callback = notify_callback
        self.scheduler = AsyncIOScheduler()
        self.diff_engine = DiffEngine()
        self._last_scan_time: Optional[datetime] = None
        self._is_running = False
    
    async def scan(
            self,
            force_notify: bool = False,
            deep_update: bool = False
    ) -> dict[str, Any]:
        """
        执行一次扫描
        
        Args:
            force_notify: 是否强制发送通知（用于手动 /check 指令）
            deep_update: 是否深度更新数据库（包含已报名活动）

        Returns:
            扫描结果统计
            :param force_notify:
            :param deep_update:
        """
        logger.info("=" * 50)
        logger.info("开始扫描第二课堂活动...")
        
        result = {
            "success": False,
            "new_db_path": None,
            "old_db_path": None,
            "activity_count": 0,
            "diff": None,
            "enrolled_changes": [],
            "error": None,
        }
        
        # 获取用于对比的旧数据库
        old_db_path = self.db_manager.get_previous_db()
        result["old_db_path"] = old_db_path
        
        # 创建新数据库文件
        new_db_path = self.db_manager.get_new_db_path()
        result["new_db_path"] = new_db_path
        logger.info(f"新数据库: {new_db_path.name}")
        
        try:
            # 在单个会话中完成所有数据获取
            # 重要：YouthService 使用 ContextVar，必须保持同一个上下文
            async with self.auth_manager.create_session_once() as service:
                logger.debug("会话已创建，开始获取数据...")
                
                # 使用 SecondClassDB 获取所有可报名活动
                db = SecondClassDB(new_db_path)
                await db.update_all_from_generator(
                    SecondClass.find(apply_ended=False),
                    expand_series=False,
                    deep_update=deep_update
                )
                
                # 更新已报名活动表
                try:
                    await db.update_enrolled_from_generator(
                        SecondClass.get_participated(),
                        deep_update=deep_update
                    )
                except Exception as e:
                    logger.warning(f"获取已报名活动失败: {e}")
                
                # 会话在此处关闭，但数据库文件已保存
            
            # 统计活动数量（在会话外执行，不涉及 YouthService）
            result["activity_count"] = await self._count_activities(new_db_path)
            logger.info(f"扫描到 {result['activity_count']} 个可报名活动")
            
            # 统计已报名数量
            enrolled_count = await self._count_enrolled(new_db_path)
            logger.info(f"已报名 {enrolled_count} 个活动")
            
            # 对比差异（如果有旧数据库）
            if old_db_path and old_db_path != new_db_path:
                diff = await self.diff_engine.diff(old_db_path, new_db_path)
                result["diff"] = diff
                logger.info(f"差异对比: {diff.get_summary()}")
                
                # 获取已报名活动的变更
                enrolled_ids = await self.diff_engine.get_enrolled_ids(new_db_path)
                enrolled_changes = diff.get_enrolled_changes(enrolled_ids)
                result["enrolled_changes"] = enrolled_changes
                
                if enrolled_changes:
                    logger.info(f"已报名活动有 {len(enrolled_changes)} 处变更")
                    
                    # 推送通知（非强制模式下只推送已报名活动的变更）
                    if not force_notify:
                        await self._send_enrolled_notifications(enrolled_changes)
                
                # 强制模式下推送所有差异
                if force_notify and self.notify_callback:
                    await self.notify_callback(diff.format_full())
            
            # 清理旧数据库
            deleted_count = self.db_manager.cleanup_old_dbs()
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧数据库")
            
            self._last_scan_time = datetime.now()
            result["success"] = True
            logger.info(f"扫描完成: {new_db_path.name}")
            
        except Exception as e:
            logger.error(f"扫描失败: {e}")
            traceback.print_exc()
            result["error"] = str(e)
            # 清理失败的数据库文件
            if new_db_path.exists():
                try:
                    new_db_path.unlink()
                    logger.debug(f"已清理失败的数据库文件: {new_db_path.name}")
                except OSError:
                    pass
            raise
        
        return result
    
    async def _count_activities(self, db_path: Path) -> int:
        """统计数据库中的活动数量"""
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM all_secondclass") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def _count_enrolled(self, db_path: Path) -> int:
        """统计已报名活动数量"""
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM enrolled_secondclass") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def _send_enrolled_notifications(self, changes: list) -> None:
        """发送已报名活动的变更通知"""
        if not self.notify_callback:
            return
        
        for change in changes:
            message = (
                f"🔔 已报名活动有更新\n\n"
                f"📝 {change.activity_name}\n"
                f"{change.format(1)}"
            )
            try:
                await self.notify_callback(message)
                logger.info(f"已发送通知: {change.activity_name}")
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
    
    def start(self) -> None:
        """启动定时任务"""
        if self._is_running:
            logger.warning("定时扫描已在运行")
            return
        
        self.scheduler.add_job(
            self.scan,
            trigger=IntervalTrigger(minutes=self.interval),
            id="activity_scan",
            replace_existing=True,
            max_instances=1,  # 防止任务重叠
        )
        self.scheduler.start()
        self._is_running = True
        logger.info(f"定时扫描已启动，间隔: {self.interval}分钟")
    
    def stop(self) -> None:
        """停止定时任务"""
        if not self._is_running:
            return
        
        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("定时扫描已停止")
    
    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._is_running
    
    def get_last_scan_time(self) -> Optional[datetime]:
        """获取上次扫描时间"""
        return self._last_scan_time
    
    def get_next_scan_time(self) -> Optional[datetime]:
        """获取下次扫描时间"""
        if not self._is_running:
            return None
        
        job = self.scheduler.get_job("activity_scan")
        if job and job.next_run_time:
            return job.next_run_time
        return None
    
    async def get_activity_list_by_id(self, activity_ids: list[str]) -> list[Activity]:
        """
        根据活动ID列表获取活动详情
        
        Args:
            activity_ids: 活动ID列表
            
        Returns:
            Activity 对象列表（仅包含成功获取的活动）
        """
        import time
        
        logger.info(f"开始获取 {len(activity_ids)} 个活动的详情...")
        
        activities: list[Activity] = []
        scan_timestamp = int(time.time())
        
        async with self.auth_manager.create_session_once() as service:
            for activity_id in activity_ids:
                try:
                    # 获取活动详情，传入 service 对象
                    sc = await SecondClass.get_secondclass_by_id(activity_id, service=service)
                    
                    # 将 SecondClass 转换为 Activity
                    activity = secondclass_to_activity(sc, scan_timestamp)
                    activities.append(activity)
                    
                    logger.debug(f"获取活动成功: {sc.name} ({activity_id})")
                    
                except Exception as e:
                    # 获取失败（活动可能已删除），跳过
                    logger.warning(f"获取活动 {activity_id} 失败，可能已删除: {e}")
                    continue
        
        logger.info(f"成功获取 {len(activities)}/{len(activity_ids)} 个活动详情")
        return activities
