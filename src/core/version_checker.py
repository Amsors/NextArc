"""版本检查器 - 基于本地 Git 仓库检查更新"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("version_checker")


@dataclass
class CommitInfo:
    """Commit 信息"""
    sha: str
    message: str
    author: str
    date: datetime
    url: str


@dataclass
class VersionUpdateResult:
    """版本更新结果"""
    current_sha: str
    latest_sha: str
    commits_behind: int
    new_commits: list[CommitInfo]
    repo_url: str


class VersionCheckConfig:
    """版本检查配置（用于类型提示，实际定义在 settings.py）"""
    enabled: bool
    day_of_week: int
    hour: int
    minute: int
    remote_name: str
    branch_name: str
    auto_fetch: bool


class VersionChecker:
    """通过本地 git 命令检查当前代码版本与远程版本的差异"""

    def __init__(self, config: VersionCheckConfig, project_root: Path):
        self.config = config
        self.project_root = project_root

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def is_git_repo(self) -> bool:
        git_dir = self.project_root / ".git"
        return git_dir.exists() and git_dir.is_dir()

    async def _run_git_command(self, args: list[str]) -> tuple[int, str, str]:
        """异步执行 git 命令
        
        Args:
            args: git 命令参数
            
        Returns:
            tuple: (returncode, stdout, stderr)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return (
                proc.returncode,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )
        except FileNotFoundError:
            logger.error("未找到 git 命令，请确保 git 已安装")
            return (1, "", "git command not found")
        except Exception as e:
            logger.error(f"执行 git 命令失败: {e}")
            return (1, "", str(e))

    async def get_current_version(self) -> Optional[str]:
        returncode, stdout, stderr = await self._run_git_command(["rev-parse", "HEAD"])
        if returncode != 0:
            logger.warning(f"获取当前版本失败: {stderr}")
            return None
        return stdout

    async def get_remote_version(self) -> Optional[str]:
        """获取远程最新 commit SHA（本地缓存的）"""
        remote_ref = f"{self.config.remote_name}/{self.config.branch_name}"
        returncode, stdout, stderr = await self._run_git_command(["rev-parse", remote_ref])
        if returncode != 0:
            logger.warning(f"获取远程版本失败: {stderr}")
            return None
        return stdout

    async def fetch_remote(self) -> bool:
        logger.debug(f"正在 fetch 远程仓库 {self.config.remote_name}...")
        returncode, stdout, stderr = await self._run_git_command(
            ["fetch", self.config.remote_name, self.config.branch_name]
        )
        if returncode != 0:
            logger.warning(f"git fetch 失败: {stderr}")
            return False
        logger.debug("git fetch 成功")
        return True

    async def get_commits_between(self, from_sha: str, to_sha: str) -> list[CommitInfo]:
        """获取两个 commit 之间的所有 commit 列表
        
        Args:
            from_sha: 起始 commit SHA
            to_sha: 结束 commit SHA
            
        Returns:
            CommitInfo 列表（按时间倒序，最新的在前）
        """
        # 格式: SHA|作者|日期|消息
        format_str = "%H|%an|%ad|%s"
        returncode, stdout, stderr = await self._run_git_command([
            "log",
            f"{from_sha}..{to_sha}",
            f"--format={format_str}",
            "--date=iso",
        ])

        if returncode != 0:
            logger.warning(f"获取 commit 列表失败: {stderr}")
            return []

        commits = []
        remote_url = await self.get_remote_url()

        for line in stdout.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            sha, author, date_str, message = parts

            try:
                # 解析 ISO 格式日期
                date = datetime.fromisoformat(date_str.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                date = datetime.now()

            # 构建 commit URL
            if remote_url:
                url = f"{remote_url}/commit/{sha}"
            else:
                url = ""

            commits.append(CommitInfo(
                sha=sha,
                message=message,
                author=author,
                date=date,
                url=url,
            ))

        return commits

    async def get_commits_behind_count(self, local_sha: str, remote_sha: str) -> int:
        """获取本地落后于远程的 commit 数量
        
        Args:
            local_sha: 本地 commit SHA
            remote_sha: 远程 commit SHA
            
        Returns:
            落后的 commit 数量
        """
        returncode, stdout, stderr = await self._run_git_command([
            "rev-list",
            "--count",
            f"{local_sha}..{remote_sha}",
        ])

        if returncode != 0:
            logger.warning(f"获取落后数量失败: {stderr}")
            return 0

        try:
            return int(stdout)
        except ValueError:
            return 0

    async def get_remote_url(self) -> str:
        returncode, stdout, stderr = await self._run_git_command(
            ["remote", "get-url", self.config.remote_name]
        )

        if returncode != 0:
            logger.warning(f"获取远程 URL 失败: {stderr}")
            return ""

        url = stdout.strip()

        # 转换 git@github.com:user/repo.git 为 https://github.com/user/repo
        if url.startswith("git@github.com:"):
            url = url.replace("git@github.com:", "https://github.com/")
        elif url.startswith("git@"):
            # 处理其他 git@ 格式
            url = url.replace(":", "/").replace("git@", "https://")

        # 移除 .git 后缀
        if url.endswith(".git"):
            url = url[:-4]

        return url

    async def check_for_updates(self) -> Optional[VersionUpdateResult]:
        """检查是否有新版本
        
        Returns:
            VersionUpdateResult: 如果有新版本，返回更新信息
            None: 如果没有新版本、已经是最新、或检查失败
        """
        if not self.is_git_repo():
            logger.warning("当前目录不是 git 仓库")
            return None

        # 获取当前本地版本
        current_sha = await self.get_current_version()
        if not current_sha:
            return None

        logger.debug(f"当前本地版本: {current_sha[:7]}")

        # 如果需要，先 fetch 远程
        if self.config.auto_fetch:
            if not await self.fetch_remote():
                logger.debug("使用本地缓存的远程引用继续检查")

        # 获取远程最新版本
        remote_sha = await self.get_remote_version()
        if not remote_sha:
            logger.warning("无法获取远程版本信息")
            return None

        logger.debug(f"远程最新版本: {remote_sha[:7]}")

        if current_sha == remote_sha:
            logger.debug("当前已是最新版本")
            return None

        commits_behind = await self.get_commits_behind_count(current_sha, remote_sha)
        if commits_behind == 0:
            logger.debug("没有检测到新版本")
            return None

        logger.info(f"检测到新版本，落后 {commits_behind} 个 commit")

        new_commits = await self.get_commits_between(current_sha, remote_sha)

        repo_url = await self.get_remote_url()

        return VersionUpdateResult(
            current_sha=current_sha,
            latest_sha=remote_sha,
            commits_behind=commits_behind,
            new_commits=new_commits,
            repo_url=repo_url,
        )
