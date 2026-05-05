"""推送偏好配置管理"""

from datetime import datetime, time
import os
from pathlib import Path
from typing import Optional, Self

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class TimeRange(BaseModel):
    start: str = Field(..., description="开始时间，格式 HH:MM")
    end: str = Field(..., description="结束时间，格式 HH:MM")

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError(f"时间格式错误: {v}，应为 HH:MM 格式，如 14:00")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        start = datetime.strptime(self.start, "%H:%M")
        end = datetime.strptime(self.end, "%H:%M")
        if start >= end:
            raise ValueError(f"时间段无效: {self.start} - {self.end}，开始时间必须早于结束时间")
        return self

    def to_time_objects(self) -> tuple[time, time]:
        start = datetime.strptime(self.start, "%H:%M").time()
        end = datetime.strptime(self.end, "%H:%M").time()
        return start, end

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"


class WeeklyTimePreference(BaseModel):
    monday: list[TimeRange] = Field(default=[], description="周一没空的时间段")
    tuesday: list[TimeRange] = Field(default=[], description="周二没空的时间段")
    wednesday: list[TimeRange] = Field(default=[], description="周三没空的时间段")
    thursday: list[TimeRange] = Field(default=[], description="周四没空的时间段")
    friday: list[TimeRange] = Field(default=[], description="周五没空的时间段")
    saturday: list[TimeRange] = Field(default=[], description="周六没空的时间段")
    sunday: list[TimeRange] = Field(default=[], description="周日没空的时间段")

    def get_day_preference(self, weekday: int) -> list[TimeRange]:
        days = [self.monday, self.tuesday, self.wednesday,
                self.thursday, self.friday, self.saturday, self.sunday]
        if 0 <= weekday <= 6:
            return days[weekday]
        return []

    def has_any_preference(self) -> bool:
        days = [self.monday, self.tuesday, self.wednesday,
                self.thursday, self.friday, self.saturday, self.sunday]
        return any(day for day in days)

    def format_preferences(self) -> str:
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
    enabled: bool = Field(default=False, description="是否启用时间筛选")

    overlap_mode: str = Field(
        default="partial",
        description="时间重叠判断模式: 'partial'(有重叠即过滤)、'full'(完全包含才过滤) 或 'threshold'(按比例阈值过滤)"
    )

    overlap_threshold: float = Field(
        default=0.5,
        description="重叠比例阈值，当 overlap_mode='threshold' 时使用，范围 0.0~1.0"
    )

    weekly_preferences: WeeklyTimePreference = Field(
        default_factory=WeeklyTimePreference,
        description="每周时间偏好"
    )

    @field_validator("overlap_mode")
    @classmethod
    def validate_overlap_mode(cls, v: str) -> str:
        if v not in ("partial", "full", "threshold"):
            raise ValueError(f"无效的 overlap_mode: {v}")
        return v

    @field_validator("overlap_threshold")
    @classmethod
    def validate_overlap_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"overlap_threshold 必须在 0.0~1.0 之间，当前值: {v}")
        return v

    def is_enabled_and_configured(self) -> bool:
        return self.enabled and self.weekly_preferences.has_any_preference()

    def get_overlap_mode_display(self) -> str:
        return {
            "partial": "有重叠即过滤",
            "full": "完全包含才过滤",
            "threshold": f"比例阈值过滤(阈值={self.overlap_threshold})"
        }.get(self.overlap_mode, "未知")


class PushPreferences(BaseModel):
    version: str = Field(default="1.0", description="配置版本")
    time_filter: TimeFilterConfig = Field(
        default_factory=TimeFilterConfig,
        description="时间筛选配置"
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> Self:
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f) or {}

        return cls(**config_dict)

    def to_yaml(self, yaml_path: Path) -> None:
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )


_preferences: Optional[PushPreferences] = None


def load_preferences(config_path: Optional[Path] = None) -> PushPreferences:
    global _preferences
    if _preferences is None:
        if config_path is None:
            env_config_path = os.getenv("NEXTARC_PREFERENCES")
            if env_config_path:
                config_path = Path(env_config_path)
            else:
                config_path = Path(__file__).parent.parent.parent / "config" / "preferences.yaml"
        _preferences = PushPreferences.from_yaml(config_path)
    return _preferences


def get_preferences() -> PushPreferences:
    if _preferences is None:
        return load_preferences()
    return _preferences


def reload_preferences(config_path: Optional[Path] = None) -> PushPreferences:
    global _preferences
    _preferences = None
    return load_preferences(config_path)
