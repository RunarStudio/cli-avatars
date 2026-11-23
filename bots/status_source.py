"""Pull status files. The first source is a git clone in the data directory.

The app fetches. It does not listen, it does not push, and it does not
create ``bot-status``. Git uses the credentials already on this machine.
This module never reads a token and never writes one. Argv is one of three
fixed lists. ``shell`` is false. A failure keeps the files already on disk.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bots.status import BotStatus, read_status_dir

DEFAULT_URL = "https://github.com/RunarStudio/cli-avatars"
DEFAULT_BRANCH = "bot-status"
DEFAULT_INTERVAL = 60
MIN_INTERVAL = 30
MAX_INTERVAL = 3600
CLONE_TIMEOUT = 45.0
FETCH_TIMEOUT = 20.0
CLONE_DIR = "status-repo"

_HTTPS = re.compile(r"^https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~-]+){2,}(?:\.git)?$")
_SSH = re.compile(r"^git@[A-Za-z0-9.-]+:[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:\.git)?$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$")


class SourceDown(Exception):
    """Fetch did not run. Local files, if any, are still readable."""


@dataclass(frozen=True)
class SourceConfig:
    kind: str = "git"
    url: str = DEFAULT_URL
    branch: str = DEFAULT_BRANCH
    interval_s: int = DEFAULT_INTERVAL
    folder: str = "status-local"

    @staticmethod
    def from_json(raw: object) -> SourceConfig:
        if not isinstance(raw, dict):
            return SourceConfig()
        kind = raw.get("kind")
        if kind not in {"git", "folder"}:
            kind = "git"
        url = raw.get("url") if valid_url(raw.get("url")) else DEFAULT_URL
        branch = raw.get("branch") if valid_branch(raw.get("branch")) else DEFAULT_BRANCH
        folder = raw.get("folder") if _relative_folder(raw.get("folder")) else "status-local"
        return SourceConfig(kind, url, branch, clamp_interval(raw.get("interval_s")), folder)


def clamp_interval(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_INTERVAL
    number = int(value)
    return min(MAX_INTERVAL, max(MIN_INTERVAL, number))


def valid_url(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 200:
        return False
    if any(ch in value for ch in " \t\r\n\\@") and not value.startswith("git@"):
        return False
    if ".." in value or " " in value or "\\" in value:
        return False
    if value.startswith("git@"):
        return _SSH.fullmatch(value) is not None
    if "@" in value:
        return False
    return _HTTPS.fullmatch(value) is not None


def valid_branch(value: object) -> bool:
    if not isinstance(value, str) or _BRANCH.fullmatch(value) is None:
        return False
    if ".." in value or "@{" in value or value.endswith("/") or value.endswith("."):
        return False
    return True


def resolve_folder(root: Path, relative: str) -> Path | None:
    """A relative folder under ``root``. Absolute paths and ``..`` are refused."""
    if not _relative_folder(relative):
        return None
    base = Path(root)
    target = (base / relative).resolve()
    try:
        base_real = base.resolve()
    except OSError:
        return None
    if target != base_real and base_real not in target.parents:
        return None
    return target


def check_argv(argv: list[str]) -> None:
    """Refuse anything except the three fetch commands. No push, no new branch."""
    if argv == checkout_argv():
        return
    if (
        len(argv) == 8
        and argv[:6] == ["git", "-C", CLONE_DIR, "fetch", "--depth", "1"]
        and argv[6] == "origin"
        and valid_branch(argv[7])
    ):
        return
    if (
        len(argv) == 9
        and argv[:5] == ["git", "clone", "--depth", "1", "--branch"]
        and argv[6] == "--single-branch"
        and argv[8] == CLONE_DIR
        and valid_branch(argv[5])
        and valid_url(argv[7])
    ):
        return
    raise SourceDown("argv")


def clone_argv(url: str, branch: str) -> list[str]:
    return ["git", "clone", "--depth", "1", "--branch", branch, "--single-branch", url, CLONE_DIR]


def fetch_argv(branch: str) -> list[str]:
    return ["git", "-C", CLONE_DIR, "fetch", "--depth", "1", "origin", branch]


def checkout_argv() -> list[str]:
    return ["git", "-C", CLONE_DIR, "checkout", "-f", "--detach", "FETCH_HEAD"]


def run_git(argv: list[str], timeout: float, cwd: Path) -> int:
    """Run one allowed git command. The return value is the exit code.

    Credentials come from the process environment git already uses.
    Stdout and stderr are discarded after the pipe is drained. They are
    not logged, because a helper can echo a URL.
    """
    check_argv(argv)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise SourceDown("timeout")
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=float(timeout),
            check=False,
            env=_git_env(),
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceDown("git") from exc
    return int(completed.returncode)


class FolderSource:
    """Status files already on disk. No git and no network."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def refresh(self, now: float) -> dict[str, BotStatus]:
        return self.read_local(now)

    def read_local(self, now: float) -> dict[str, BotStatus]:
        return read_status_dir(self.folder / "status", now)


class GitFolderSource:
    """Clone ``url`` at ``branch`` under ``bots_dir`` and fetch on demand."""

    def __init__(self, bots_dir: Path, url: str, branch: str, runner=None):
        self.bots_dir = Path(bots_dir)
        self.url = url if valid_url(url) else DEFAULT_URL
        self.branch = branch if valid_branch(branch) else DEFAULT_BRANCH
        self.runner = run_git if runner is None else runner
        self.down = False

    def refresh(self, now: float) -> dict[str, BotStatus]:
        try:
            self._update()
        except SourceDown:
            self.down = True
        else:
            self.down = False
        return self.read_local(now)

    def read_local(self, now: float) -> dict[str, BotStatus]:
        return read_status_dir(self.bots_dir / CLONE_DIR / "status", now)

    def _update(self) -> None:
        if not valid_url(self.url) or not valid_branch(self.branch):
            raise SourceDown("config")
        self.bots_dir.mkdir(parents=True, exist_ok=True)
        dest = self.bots_dir / CLONE_DIR
        if (dest / ".git").is_dir() and not (dest / ".git").is_symlink():
            self._run(fetch_argv(self.branch), FETCH_TIMEOUT)
            self._run(checkout_argv(), FETCH_TIMEOUT)
            return
        if dest.exists():
            raise SourceDown("dest")
        self._run(clone_argv(self.url, self.branch), CLONE_TIMEOUT)

    def _run(self, argv: list[str], timeout: float) -> None:
        check_argv(argv)
        try:
            code = self.runner(argv, timeout, self.bots_dir)
        except SourceDown:
            raise
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SourceDown("git") from exc
        if code != 0:
            raise SourceDown("git")


class FetchScheduler:
    """Call ``source.refresh`` on an interval. The minimum is 30 seconds."""

    def __init__(self, source, interval_s: object):
        self.source = source
        self.interval = float(clamp_interval(interval_s))
        self._next: float | None = None
        self._last: dict[str, BotStatus] = {}

    def tick(self, now: float) -> dict[str, BotStatus]:
        if self._next is None or now >= self._next:
            try:
                self._last = self.source.refresh(now)
            except Exception:
                reader = getattr(self.source, "read_local", None)
                self._last = reader(now) if reader is not None else {}
            self._next = now + self.interval
        return dict(self._last)


def _git_env() -> dict[str, str]:
    """The current environment, plus a flag that stops an interactive prompt.

    Nothing is added that would carry a new token. Existing helper variables
    stay so git can use credentials it already has.
    """
    env = {key: value for key, value in os.environ.items() if isinstance(value, str)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _relative_folder(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 80:
        return False
    if value.startswith(("/", "\\")) or ":" in value:
        return False
    parts = Path(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    return True
