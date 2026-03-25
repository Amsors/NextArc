"""推送偏好配置管理

用于管理用户的推送偏好设置，包括时间筛选、活动类型筛选等。
"""

from datetime import datetime, time
from pathlib import Path
from typing import Optional, Self

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class TimeRange(BaseModel):
    """时间段配置"""
    start: str = Field(..., description="开始时间，格式 HH:MM")
    end: str = Field(..., description="结束时间，格式 HH:MM")

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """验证时间格式"""
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError(f"时间格式错误: {v}，应为 HH:MM 格式，如 14:00")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        """验证开始时间早于结束时间"""
        start = datetime.strptime(self.start, "%H:%M")
        end = datetime.strptime(self.end, "%H:%M")
        if start >= end:
            raise ValueError(f"时间段无效: {self.start} - {self.end}，开始时间必须早于结束时间")
        return self

    def to_time_objects(self) -> tuple[time, time]:
        """转换为 time 对象"""
        start = datetime.strptime(self.start, "%H:%M").time()
        end = datetime.strptime(self.end, "%H:%M").time()
        return start, end

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"


class WeeklyTimePreference(BaseModel):
    """每周时间偏好配置"""
    monday: list[TimeRange] = Field(default=[], description="周一没空的时间段")
    tuesday: list[TimeRange] = Field(default=[], description="周二没空的时间段")
    wednesday: list[TimeRange] = Field(default=[], description="周三没空的时间段")
    thursday: list[TimeRange] = Field(default=[], description="周四没空的时间段")
    friday: list[TimeRange] = Field(default=[], description="周五没空的时间段")
    saturday: list[TimeRange] = Field(default=[], description="周六没空的时间段")
    sunday: list[TimeRange] = Field(default=[], description="周日没空的时间段")

    def get_day_preference(self, weekday: int) -> list[TimeRange]:
        """
        获取指定星期几的时间偏好
        
        Args:
            weekday: 星期几（0=周一，6=周日）
            
        Returns:
            该日期没空的时间段列表
        """
        days = [self.monday, self.tuesday, self.wednesday,
                self.thursday, self.friday, self.saturday, self.sunday]
        if 0 <= weekday <= 6:
            return days[weekday]
        return []

    def has_any_preference(self) -> bool:
        """检查是否有任何时间偏好配置"""
        days = [self.monday, self.tuesday, self.wednesday,
                self.thursday, self.friday, self.saturday, self.sunday]
        return any(day for day in days)

    def format_preferences(self) -> str:
        """格式化显示所有时间偏好"""
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        days = [self.monday, self.tuesday, self.wednesday,
                self.thursday, self.friday, self.saturday, self.sunday]

        lines = []
        for i, (name, ranges) in enumerate(zip(day_names, days)):
            if ranges:
                ranges_str = ", ".join(str(r) for r in ranges)
                lines.append(f"  {name}: {ranges_str}")

        return "\n".join(lines) if lines else "  （未配置）"


class TimeFilterConfig(BaseModel):
    """时间筛选器配置"""
    enabled: bool = Field(default=False, description="是否启用时间筛选")

    # 时间重叠判断模式
    overlap_mode: str = Field(
        default="partial",
        description="时间重叠判断模式: 'partial'(有重叠即过滤)、'full'(完全包含才过滤) 或 'threshold'(按比例阈值过滤)"
    )

    # 重叠比例阈值（仅当 overlap_mode 为 "threshold" 时使用）
    overlap_threshold: float = Field(
        default=0.5,
        description="重叠比例阈值，当 overlap_mode='threshold' 时使用，范围 0.0~1.0，表示冲突时间占活动总时长的比例"
    )

    weekly_preferences: WeeklyTimePreference = Field(
        default_factory=WeeklyTimePreference,
        description="每周时间偏好"
    )

    @field_validator("overlap_mode")
    @classmethod
    def validate_overlap_mode(cls, v: str) -> str:
        """验证重叠模式"""
        valid_modes = ["partial", "full", "threshold"]
        if v not in valid_modes:
            raise ValueError(f"无效的 overlap_mode: {v}，必须是 {valid_modes} 之一")
        return v

    @field_validator("overlap_threshold")
    @classmethod
    def validate_overlap_threshold(cls, v: float) -> float:
        """验证重叠比例阈值"""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"overlap_threshold 必须在 0.0~1.0 之间，当前值: {v}")
        return v

    def is_enabled_and_configured(self) -> bool:
        """检查是否启用且有配置"""
        return self.enabled and self.weekly_preferences.has_any_preference()

    def get_overlap_mode_display(self) -> str:
        """获取重叠模式的显示文本"""
        return {
            "partial": "有重叠即过滤",
            "full": "完全包含才过滤",
            "threshold": f"比例阈值过滤(阈值={self.overlap_threshold})"
        }.get(self.overlap_mode, "未知")


class PushPreferences(BaseModel):
    """推送偏好配置"""
    version: str = Field(default="1.0", description="配置版本")
    time_filter: TimeFilterConfig = Field(
        default_factory=TimeFilterConfig,
        description="时间筛选配置"
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> Self:
        """从 YAML 文件加载配置"""
        if not yaml_path.exists():
            # 返回默认配置
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}

        return cls(**config_dict)

    def to_yaml(self, yaml_path: Path) -> None:
        """保存配置到 YAML 文件"""
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )


# 全局配置实例
_preferences: Optional[PushPreferences] = None


def load_preferences(config_path: Optional[Path] = None) -> PushPreferences:
    """加载推送偏好配置"""
    global _preferences
    if _preferences is None:
        if config_path is None:
            # 默认路径：项目根目录下的 config/preferences.yaml
            config_path = Path(__file__).parent.parent.parent / "config" / "preferences.yaml"
        _preferences = PushPreferences.from_yaml(config_path)
    return _preferences


def get_preferences() -> PushPreferences:
    """获取已加载的推送偏好配置"""
    if _preferences is None:
        return load_preferences()
    return _preferences


def reload_preferences(config_path: Optional[Path] = None) -> PushPreferences:
    """重新加载推送偏好配置"""
    global _preferences
    _preferences = None
    return load_preferences(config_path)
