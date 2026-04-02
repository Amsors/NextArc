"""数据库版本管理器"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("db_manager")


class DatabaseManager:
    DB_PATTERN = re.compile(r"secondclass_(\d{8})_(\d{6})\.db$")

    def __init__(self, data_dir: Path, max_history: int = 10):
        self.data_dir = Path(data_dir)
        self.max_history = max_history
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"数据目录: {self.data_dir.absolute()}")

    def get_new_db_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path = self.data_dir / f"secondclass_{timestamp}.db"
        logger.debug(f"新数据库路径: {db_path}")
        return db_path

    def list_db_files(self) -> list[Path]:
        dbs = []
        for f in self.data_dir.iterdir():
            if f.is_file() and self.DB_PATTERN.match(f.name):
                dbs.append(f)
        return sorted(dbs, key=lambda x: x.name, reverse=True)

    def get_latest_db(self) -> Optional[Path]:
        dbs = self.list_db_files()
        return dbs[0] if dbs else None

    def get_previous_db(self) -> Optional[Path]:
        dbs = self.list_db_files()
        return dbs[0] if dbs else None

    def cleanup_old_dbs(self) -> int:
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
        return len(self.list_db_files())

    def get_db_info(self) -> dict:
        dbs = self.list_db_files()
        return {
            "total": len(dbs),
            "max_history": self.max_history,
            "latest": dbs[0].name if dbs else None,
            "all_files": [db.name for db in dbs],
        }
