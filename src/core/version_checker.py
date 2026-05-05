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
    sha: str
    message: str
    author: str
    date: datetime
    url: str


@dataclass
class VersionUpdateResult:
    current_sha: str
    latest_sha: str
    commits_behind: int
    new_commits: list[CommitInfo]
    repo_url: str


class VersionCheckConfig:
    enabled: bool
    day_of_week: int
    hour: int
    minute: int
    remote_name: str
    branch_name: str
    auto_fetch: bool


class VersionChecker:
    def __init__(self, config: VersionCheckConfig, project_root: Path):
        self.config = config
        self.project_root = project_root

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def is_git_repo(self) -> bool:
        git_dir = self.project_root / ".git"
        return git_dir.exists() and git_dir.is_dir()

    @property
    def target_remote_ref(self) -> str:
        return f"{self.config.remote_name}/{self.config.branch_name}"

    def _build_git_command_args(self, args: list[str]) -> list[str]:
        safe_directory = str(self.project_root.resolve())
        return ["-c", f"safe.directory={safe_directory}", *args]

    async def _run_git_command(self, args: list[str]) -> tuple[int, str, str]:
        git_args = self._build_git_command_args(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *git_args,
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

    async def get_current_branch(self) -> Optional[str]:
        returncode, stdout, stderr = await self._run_git_command(["branch", "--show-current"])
        if returncode != 0:
            logger.warning(f"获取当前分支失败: {stderr}")
            return None
        return stdout or None

    async def get_remote_version(self) -> Optional[str]:
        remote_ref = self.target_remote_ref
        logger.debug(f"获取远程版本: {remote_ref}")
        returncode, stdout, stderr = await self._run_git_command(["rev-parse", remote_ref])
        if returncode != 0:
            logger.warning(f"获取远程版本失败: {stderr}")
            return None
        return stdout

    async def fetch_remote(self) -> bool:
        remote_refspec = (
            f"+refs/heads/{self.config.branch_name}:"
            f"refs/remotes/{self.config.remote_name}/{self.config.branch_name}"
        )
        logger.debug(f"正在 fetch 远程仓库 {self.target_remote_ref}...")
        returncode, stdout, stderr = await self._run_git_command(
            ["fetch", self.config.remote_name, remote_refspec]
        )
        if returncode != 0:
            logger.warning(f"git fetch 失败: {stderr}")
            return False
        logger.info("git fetch 成功")
        return True

    async def local_branch_exists(self, branch_name: str | None = None) -> bool:
        branch = branch_name or self.config.branch_name
        returncode, _stdout, _stderr = await self._run_git_command(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]
        )
        return returncode == 0

    async def switch_to_target_branch(self) -> tuple[int, str, str]:
        current_branch = await self.get_current_branch()
        target_branch = self.config.branch_name

        if current_branch == target_branch:
            logger.info(f"当前已经在目标分支 {target_branch}")
            return (0, "", "")

        if await self.local_branch_exists(target_branch):
            logger.info(f"切换到本地目标分支 {target_branch}")
            return await self._run_git_command(["switch", target_branch])

        logger.info(f"创建并切换到跟踪分支 {target_branch} -> {self.target_remote_ref}")
        return await self._run_git_command(
            ["switch", "--track", "-c", target_branch, self.target_remote_ref]
        )

    async def get_commits_between(self, from_sha: str, to_sha: str) -> list[CommitInfo]:
        logger.debug(f"获取 commit 列表: {from_sha[:7]}..{to_sha[:7]}")
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
                date = datetime.fromisoformat(date_str.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                date = datetime.now()

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

        logger.debug(f"解析到 {len(commits)} 个 commit")
        return commits

    async def get_commits_behind_count(self, local_sha: str, remote_sha: str) -> int:
        logger.debug(f"计算落后数量...")
        returncode, stdout, stderr = await self._run_git_command([
            "rev-list",
            "--count",
            f"{local_sha}..{remote_sha}",
        ])

        if returncode != 0:
            logger.warning(f"获取落后数量失败: {stderr}")
            return 0

        try:
            count = int(stdout)
            logger.debug(f"落后数量: {count}")
            return count
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

        if url.startswith("git@github.com:"):
            url = url.replace("git@github.com:", "https://github.com/")
        elif url.startswith("git@"):
            url = url.replace(":", "/").replace("git@", "https://")

        if url.endswith(".git"):
            url = url[:-4]

        logger.debug(f"远程 URL: {url}")
        return url

    async def check_for_updates(self) -> Optional[VersionUpdateResult]:
        logger.info("开始检查版本更新...")
        logger.info(f"项目目录: {self.project_root}")

        if not self.is_git_repo():
            logger.warning("当前目录不是 git 仓库")
            return None

        logger.info("确认是 git 仓库")

        current_sha = await self.get_current_version()
        if not current_sha:
            logger.warning("无法获取当前本地版本")
            return None

        logger.info(f"当前本地版本: {current_sha[:7]}")

        if self.config.auto_fetch:
            logger.info(f"auto_fetch 启用，正在 fetch {self.config.remote_name}...")
            fetch_success = await self.fetch_remote()
            if not fetch_success:
                logger.warning("fetch 失败，使用本地缓存的远程引用继续检查")
        else:
            logger.info("auto_fetch 禁用，使用本地缓存的远程引用")

        remote_sha = await self.get_remote_version()
        if not remote_sha:
            logger.warning("无法获取远程版本信息")
            return None

        logger.info(f"远程最新版本: {remote_sha[:7]}")

        if current_sha == remote_sha:
            logger.info("当前已是最新版本")
            return None

        commits_behind = await self.get_commits_behind_count(current_sha, remote_sha)
        logger.info(f"落后 commit 数量: {commits_behind}")

        if commits_behind == 0:
            logger.info("没有检测到新版本")
            return None

        logger.info(f"检测到新版本，落后 {commits_behind} 个 commit")

        new_commits = await self.get_commits_between(current_sha, remote_sha)
        logger.info(f"获取到 {len(new_commits)} 个 commit 详情")

        repo_url = await self.get_remote_url()
        logger.info(f"仓库 URL: {repo_url}")

        return VersionUpdateResult(
            current_sha=current_sha,
            latest_sha=remote_sha,
            commits_behind=commits_behind,
            new_commits=new_commits,
            repo_url=repo_url,
        )
