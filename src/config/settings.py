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
    scan_on_start: bool = False


class FilterConfig(BaseModel):
    """过滤配置"""
    ignore_participated_but_ended_activity: bool = True


class MonitorConfig(BaseModel):
    """监控配置"""
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    notify_new_activities: bool = Field(default=True, description="发现新活动时发送飞书通知")
    use_ai_filter: bool = Field(default=False, description="是否使用 AI 筛选新活动")


class FeishuConfig(BaseModel):
    """飞书配置"""
    app_id: str = ""
    app_secret: str = ""
    chat_id: str = Field(default="",
                         description="预配置的私聊会话ID，格式如 oc_xxx。若配置，则机器人启动即可发送消息，无需等待用户先发消息")
    max_activities_per_card: int = Field(
        default=20,
        ge=1,
        le=100,
        description="每条消息最多显示的活动数量，超过则分多条消息发送（用于避免超出飞书消息长度限制）"
    )


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


class DatabaseConfig(BaseModel):
    """数据库配置
    
    所有路径都相对于项目根目录解析
    """
    data_dir: Path = Path("./data")
    max_history: int = Field(default=10, ge=1, le=100)
    preference_db_path: Optional[Path] = Field(
        default=None,
        description="用户偏好数据库文件路径，默认使用 data_dir/user_preference.db"
    )

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, v: Path) -> Path:
        """将相对路径转换为相对于项目根目录的绝对路径"""
        path = Path(v)
        if not path.is_absolute():
            path = get_project_root() / path
        return path.resolve()

    @field_validator("preference_db_path")
    @classmethod
    def resolve_preference_db_path(cls, v: Optional[Path]) -> Optional[Path]:
        """将相对路径转换为相对于项目根目录的绝对路径"""
        if v is None:
            return None
        path = Path(v)
        if not path.is_absolute():
            path = get_project_root() / path
        return path.resolve()

    def get_preference_db_path(self) -> Path:
        """获取用户偏好数据库的完整路径"""
        if self.preference_db_path is not None:
            return self.preference_db_path
        return self.data_dir / "user_preference.db"


class LogFileConfig(BaseModel):
    """日志文件配置"""
    enabled: bool = Field(default=False, description="是否启用文件日志")
    path: Path = Field(default=Path("./logs/nextarc.log"), description="日志文件路径")
    max_size_mb: int = Field(default=10, ge=1, le=1000, description="单个日志文件最大大小（MB）")
    backup_count: int = Field(default=5, ge=0, le=100, description="保留的历史日志文件数量")

    @field_validator("path")
    @classmethod
    def resolve_log_path(cls, v: Path) -> Path:
        path = Path(v)
        if not path.is_absolute():
            path = get_project_root() / path
        return path.resolve()


class LogConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: LogFileConfig = Field(default_factory=LogFileConfig, description="文件日志配置")


class AIRateLimitConfig(BaseModel):
    """AI API 速率限制配置"""
    requests_per_minute: int = Field(
        default=0,
        ge=0,
        description="每分钟最大请求数（0表示不限制）"
    )
    max_concurrency: int = Field(
        default=3,
        ge=1,
        le=100,
        description="最大并发数"
    )
    enable_queue: bool = Field(
        default=True,
        description="达到速率限制时是否排队等待"
    )
    queue_timeout: float = Field(
        default=300.0,
        ge=0,
        description="队列最大等待时间（秒）"
    )


class AIRetryConfig(BaseModel):
    """AI API 重试配置"""
    max_retries: int = Field(
        default=3,
        ge=0,
        le=20,
        description="最大重试次数"
    )
    base_delay: float = Field(
        default=2.0,
        ge=0,
        description="基础重试延迟（秒）"
    )
    max_delay: float = Field(
        default=60.0,
        ge=0,
        description="最大重试延迟（秒）"
    )
    backoff_factor: float = Field(
        default=2.0,
        ge=1.0,
        description="退避倍数（指数退避：delay = base_delay * (backoff_factor ^ attempt)）"
    )
    retry_on_status: list[int] = Field(
        default=[429, 500, 502, 503, 504],
        description="触发重试的HTTP状态码列表"
    )
    retry_on_network_error: bool = Field(
        default=True,
        description="网络错误是否重试"
    )


class AIConfig(BaseModel):
    """AI 筛选配置
    
    启用 AI 功能时，api_key、model、user_info、system_prompt_file、
    user_prompt_template_file、temperature 必须配置
    """
    enabled: bool = Field(default=False, description="是否启用 AI 筛选")

    api_key: str = Field(default="", description="API 密钥（enabled: true 时必填）")
    base_url: str = Field(default="", description="API 基础 URL（可选，用于第三方兼容服务）")
    model: str = Field(default="", description="模型名称（enabled: true 时必填，如：gpt-3.5-turbo）")
    user_info: str = Field(
        default="",
        description="用户偏好描述（enabled: true 时必填），用于指导 AI 筛选"
    )

    system_prompt_file: str = Field(
        default="config/prompts/system_prompt.txt",
        description="系统提示词文件路径（enabled: true 时必填）"
    )
    user_prompt_template_file: str = Field(
        default="config/prompts/user_prompt_template.txt",
        description="用户提示词模板文件路径（enabled: true 时必填）"
    )
    temperature: Optional[float] = Field(
        default=None,
        description="采样温度（enabled: true 时必填，0.0-2.0，建议 0.3）"
    )
    timeout: int = Field(default=30, ge=5, le=300, description="请求超时时间（秒，可选）")

    extra_body: Optional[dict] = Field(
        default=None,
        description="额外的 API 请求体参数，用于第三方 API 扩展功能（如 Kimi 的 thinking 控制）"
    )

    rate_limit: AIRateLimitConfig = Field(
        default_factory=AIRateLimitConfig,
        description="速率限制配置"
    )
    # 重试配置（可选）
    retry: AIRetryConfig = Field(
        default_factory=AIRetryConfig,
        description="重试配置"
    )

    def validate_required_fields(self) -> None:
        """验证必填字段（当 enabled: true 时调用）"""
        if not self.enabled:
            return

        missing = []
        if not self.api_key:
            missing.append("api_key")
        if not self.model:
            missing.append("model")
        if not self.user_info:
            missing.append("user_info")
        if not self.system_prompt_file:
            missing.append("system_prompt_file")
        if not self.user_prompt_template_file:
            missing.append("user_prompt_template_file")
        if self.temperature is None:
            missing.append("temperature")

        if missing:
            raise ValueError(
                f"AI 功能已启用，但以下配置项未填写：{', '.join(missing)}"
            )


class Settings(BaseSettings):
    """全局配置"""
    ustc: USTCConfig = USTCConfig()
    filter: FilterConfig = FilterConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    monitor: MonitorConfig = MonitorConfig()
    feishu: FeishuConfig = FeishuConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LogConfig = LogConfig()
    ai: AIConfig = AIConfig()

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


_settings: Optional[Settings] = None


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """加载配置，如果已加载则返回缓存"""
    global _settings
    if _settings is None:
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "config.yaml"
        _settings = Settings.from_yaml(config_path)
        _settings.ensure_directories()
    return _settings


def get_settings() -> Settings:
    """获取已加载的配置"""
    if _settings is None:
        raise RuntimeError("配置尚未加载，请先调用 load_settings()")
    return _settings


def load_prompt_file(file_path: str, default_content: str = "") -> str:
    """加载提示词文件
    
    支持相对路径（相对于项目根目录）和绝对路径
    """
    project_root = Path(__file__).parent.parent.parent
    path = Path(file_path)
    if not path.is_absolute():
        path = project_root / file_path

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else default_content
        except Exception as e:
            print(f"警告：读取提示词文件失败 {path}: {e}")
            return default_content
    else:
        print(f"提示：提示词文件不存在 {path}，使用默认内容")
        return default_content


def load_prompt_file_strict(file_path: str) -> str:
    """严格加载提示词文件（文件必须存在且不为空）
    
    支持相对路径（相对于项目根目录）和绝对路径
    
    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 如果文件内容为空
    """
    project_root = Path(__file__).parent.parent.parent
    path = Path(file_path)
    if not path.is_absolute():
        path = project_root / file_path

    if not path.exists():
        raise FileNotFoundError(
            f"提示词文件不存在: {path}\n"
            f"配置文件中的路径: {file_path}\n"
            f"请创建该文件或修改配置文件中的路径"
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError(f"提示词文件内容为空: {path}")
            return content
    except FileNotFoundError:
        raise FileNotFoundError(
            f"提示词文件不存在: {path}\n"
            f"配置文件中的路径: {file_path}\n"
            f"请创建该文件或修改配置文件中的路径"
        )
    except Exception as e:
        raise RuntimeError(f"读取提示词文件失败 {path}: {e}")
