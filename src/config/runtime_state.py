"""部署运行态配置持久化。"""

import os
from pathlib import Path
from typing import Any

import yaml


def get_state_path() -> Path:
    """返回 NextArc 运行态配置文件路径。"""

    env_path = os.getenv("NEXTARC_STATE")
    if env_path:
        return Path(env_path)

    state_dir = os.getenv("NEXTARC_STATE_DIR", "/var/lib/nextarc")
    return Path(state_dir) / "state.yaml"


class RuntimeState:
    """保存可安全跨重启复用的运行态信息。"""

    def __init__(self, path: Path | None = None):
        self.path = path or get_state_path()
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.data = {}
            return

        with open(self.path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)
        self.path.chmod(0o600)

    def get(self, key: str, default: str = "") -> str:
        value = self.data.get(key, default)
        return value if isinstance(value, str) else default

    def set_if_changed(self, key: str, value: str | None) -> bool:
        if not value or self.data.get(key) == value:
            return False

        self.data[key] = value
        self.save()
        return True
