"""版本更新事件定义"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    date: datetime
    url: str


@dataclass
class VersionUpdateEvent:
    current_sha: str
    latest_sha: str
    commits_behind: int
    new_commits: list[CommitInfo] = field(default_factory=list)
    repo_url: str = ""
