"""配置管理模块"""

import os
from pathlib import Path
from typing import Literal, Optional, Self, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class USTCConfig(BaseModel):
    """USTC 认证配置"""
    auth_mode: Literal["file", "env"] = "file"
    username: Optional[str] = None
    password: Optional[str] = None
    env_username: str = "USTC_USERNAME"
    env_password: str = "USTC_PASSWORD"

class BehaviorConfig(BaseModel):
    """应用行为配置"""
    scan_on_start: bool = True

class FilterConfig(BaseModel):
    """过滤配置"""
    ignore_participated_but_ended_activity: bool = True

class MonitorConfig(BaseModel):
    """监控配置"""
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    notify_new_activities: bool = Field(default=True, description="发现新活动时发送飞书通知")


class FeishuConfig(BaseModel):
    """飞书配置"""
    app_id: str = ""
    app_secret: str = ""


class DatabaseConfig(BaseModel):
    """数据库配置"""
    data_dir: Path = Path("./data")
    max_history: int = Field(default=10, ge=1, le=100)
    
    @field_validator("data_dir")
    @classmethod
    def ensure_path(cls, v: Path) -> Path:
        return Path(v)


class LogConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"


class Settings(BaseSettings):
    """全局配置"""
    ustc: USTCConfig = USTCConfig()
    filter: FilterConfig = FilterConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    monitor: MonitorConfig = MonitorConfig()
    feishu: FeishuConfig = FeishuConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LogConfig = LogConfig()
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> Self:
        """从 YAML 文件加载配置"""
        if not yaml_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {yaml_path}")
        
        with open(yaml_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
        
        return cls(**config_dict)
    
    def get_credentials(self) -> Tuple[str, str]:
        """根据 auth_mode 获取用户名密码"""
        if self.ustc.auth_mode == "env":
            username = os.getenv(self.ustc.env_username)
            password = os.getenv(self.ustc.env_password)
            if not username or not password:
                raise ValueError(
                    f"环境变量中未找到 USTC 凭据，"
                    f"请检查 {self.ustc.env_username} 和 {self.ustc.env_password} 是否已设置"
                )
            return username, password
        else:
            if not self.ustc.username or not self.ustc.password:
                raise ValueError("配置文件中未设置 USTC 凭据（username 和 password）")
            return self.ustc.username, self.ustc.password
    
    def ensure_directories(self) -> None:
        """确保必要的目录存在"""
        self.database.data_dir.mkdir(parents=True, exist_ok=True)


# 全局配置实例
_settings: Optional[Settings] = None


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """加载配置，如果已加载则返回缓存"""
    global _settings
    if _settings is None:
        if config_path is None:
            # 默认从当前文件所在目录加载
            config_path = Path(__file__).parent / "config.yaml"
        _settings = Settings.from_yaml(config_path)
        _settings.ensure_directories()
    return _settings


def get_settings() -> Settings:
    """获取已加载的配置"""
    if _settings is None:
        raise RuntimeError("配置尚未加载，请先调用 load_settings()")
    return _settings
