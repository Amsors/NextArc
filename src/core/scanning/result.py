"""扫描流程输入与结果对象。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.diff_result import ActivityChange, DiffResult


@dataclass
class ScanOptions:
    """一次扫描运行的显式选项。"""

    deep_update: bool
    notify_diff: bool
    notify_enrolled_change: bool
    notify_new_activities: bool
    no_filter: bool
    wait_for_notifications: bool = False


@dataclass
class SyncResult:
    """活动同步和快照写入结果。"""

    target_db: Path
    activity_count: int = 0
    enrolled_count: int = 0
    enrolled_error: str | None = None


@dataclass
class ScanResult:
    """完整扫描结果。"""

    success: bool = False
    new_db_path: Path | None = None
    old_db_path: Path | None = None
    activity_count: int = 0
    enrolled_count: int = 0
    diff: DiffResult | None = None
    enrolled_changes: list[ActivityChange] = field(default_factory=list)
    error: str | None = None
    notification_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """返回兼容旧 scanner.scan 调用方的字典结构。"""

        return {
            "success": self.success,
            "new_db_path": self.new_db_path,
            "old_db_path": self.old_db_path,
            "activity_count": self.activity_count,
            "enrolled_count": self.enrolled_count,
            "diff": self.diff,
            "enrolled_changes": self.enrolled_changes,
            "error": self.error,
            "notification_errors": self.notification_errors,
        }
