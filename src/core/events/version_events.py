"""版本更新事件定义"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommitInfo:
    """Commit 信息"""
    sha: str  # commit SHA
    message: str  # commit message（第一行）
    author: str  # 作者名
    date: datetime  # 提交时间
    url: str  # commit URL


@dataclass
class VersionUpdateEvent:
    """发现新版本事件
    
    当版本检查器发现本地版本落后于远程版本时触发
    
    Attributes:
        current_sha: 本地当前版本 SHA
        latest_sha: 远程最新版本 SHA
        commits_behind: 落后 commit 数量
        new_commits: 新增 commit 列表（按时间倒序）
        repo_url: 仓库地址
    """
    current_sha: str
    latest_sha: str
    commits_behind: int
    new_commits: list[CommitInfo] = field(default_factory=list)
    repo_url: str = ""
