"""数据库版本管理器"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("db_manager")


class DatabaseManager:
    """
    数据库版本管理器
    - 管理带时间戳的数据库文件
    - 自动清理过期历史文件
    """

    DB_PATTERN = re.compile(r"secondclass_(\d{8})_(\d{6})\.db$")

    def __init__(self, data_dir: Path, max_history: int = 10):
        self.data_dir = Path(data_dir)
        self.max_history = max_history
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"数据目录: {self.data_dir.absolute()}")

    def get_new_db_path(self) -> Path:
        """生成新的数据库文件路径（带时间戳）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path = self.data_dir / f"secondclass_{timestamp}.db"
        logger.debug(f"新数据库路径: {db_path}")
        return db_path

    def list_db_files(self) -> list[Path]:
        """
        列出所有数据库文件，按时间倒序（最新的在前）
        
        Returns:
            按时间戳倒序排列的数据库文件路径列表
        """
        dbs = []
        for f in self.data_dir.iterdir():
            if f.is_file() and self.DB_PATTERN.match(f.name):
                dbs.append(f)
        # 按文件名中的时间戳倒序
        return sorted(dbs, key=lambda x: x.name, reverse=True)

    def get_latest_db(self) -> Optional[Path]:
        """
        获取最新的数据库文件
        
        Returns:
            最新的数据库文件路径，如果没有则返回 None
        """
        dbs = self.list_db_files()
        return dbs[0] if dbs else None

    def get_previous_db(self) -> Optional[Path]:
        """
        获取用于对比的上一份数据库
        
        Returns:
            上一份数据库文件路径，如果没有则返回 None
        """
        dbs = self.list_db_files()
        # 返回最新的一个（如果存在）
        return dbs[0] if dbs else None

    def cleanup_old_dbs(self) -> int:
        """
        清理超出保留数量的旧数据库
        
        Returns:
            删除的文件数量
        """
        dbs = self.list_db_files()
        deleted_count = 0

        if len(dbs) > self.max_history:
            for old_db in dbs[self.max_history:]:
                try:
                    old_db.unlink()
                    deleted_count += 1
                    logger.info(f"已删除旧数据库: {old_db.name}")
                except OSError as e:
                    logger.error(f"删除数据库失败 {old_db.name}: {e}")

        return deleted_count

    def get_db_count(self) -> int:
        """获取当前数据库文件数量"""
        return len(self.list_db_files())

    def get_db_info(self) -> dict:
        """获取数据库统计信息"""
        dbs = self.list_db_files()
        return {
            "total": len(dbs),
            "max_history": self.max_history,
            "latest": dbs[0].name if dbs else None,
            "all_files": [db.name for db in dbs],
        }
