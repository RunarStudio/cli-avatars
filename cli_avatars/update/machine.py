"""Fetch ``dev``, and stage a new build when that commit is newer.

Steps, in order, and only when the previous step succeeded:

1. ``git fetch origin dev``
2. Compare ``origin/dev`` with the installed commit.
3. ``git pull --ff-only origin dev`` when dev is a descendant.
4. ``overlay.py --selftest`` and ``--bootcheck-only`` from the clone.
5. PyInstaller onedir into a staging directory beside the install.

The swap itself runs in a helper after this process exits, so the
install directory is not renamed while the app is still open. Every
command is a fixed argument list. Nothing from chat is executed.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cli_avatars.bootcheck import stamp_now
from cli_avatars.update.config import CHANNEL, UpdateConfig, normalize_repo_url
from cli_avatars.update.proc import RunResult, git_env
from cli_avatars.update.version import (
    NEWER,
    SAME,
    STAMP_NAME,
    _hex,
    commit_relation,
    same_commit,
    short_commit,
    version_in_tree,
    write_stamp,
)

Runner = Callable[..., RunResult]
StatusFn = Callable[[str], None]

FETCH_TIMEOUT_S = 120.0
PULL_TIMEOUT_S = 180.0
CHECK_TIMEOUT_S = 180.0
BUILD_TIMEOUT_S = 900.0
PROBE_TIMEOUT_S = 20.0

COLLECT_NAME = "CLI Avatars"
EXE_NAME = "cli-avatars.exe"
SRC_DIR = "src"
STATE_NAME = "update_state.json"
LOG_NAME = "update.log"
WORK_DIR = "update-work"

PHASE_BLOCKED = "blocked"
PHASE_CURRENT = "up_to_date"
PHASE_STAGED = "staged"
PHASE_FAILED = "failed"


@dataclass(frozen=True)
class Toolchain:
    """Programs the update is allowed to run. ``reason`` disables the button."""

    git: str | None
    python: tuple[str, ...]
    pyinstaller: bool
    reason: str


@dataclass(frozen=True)
class UpdateResult:
    """What the state machine decided. ``message`` is ours, not process output."""

    phase: str
    message: str
    installed_commit: str
    upstream_commit: str
    staging: Path | None
    helper_argv: tuple[str, ...]
    helper_cwd: Path | None


def run_update(
    *,
    data_dir: Path,
    install_dir: Path,
    settings: UpdateConfig,
    installed_commit: str,
    toolchain: Toolchain,
    runner: Runner,
    on_status: StatusFn | None = None,
) -> UpdateResult:
    """Run one update check. ``runner`` is ``run_fixed`` in production."""
    if toolchain.reason:
        return _done(PHASE_BLOCKED, toolchain.reason, installed_commit, "")
    if settings.error or not normalize_repo_url(settings.repo_url) or settings.channel != CHANNEL:
        return _done(PHASE_BLOCKED, settings.error or "update settings are not usable", installed_commit, "")
    if not toolchain.git or not toolchain.python or not toolchain.pyinstaller:
        return _done(PHASE_BLOCKED, "git or PyInstaller is missing", installed_commit, "")
    overlap = _overlap_reason(install_dir, data_dir)
    if overlap:
        return _done(PHASE_BLOCKED, overlap, installed_commit, "")

    log_path = data_dir / LOG_NAME
    src = data_dir / SRC_DIR
    work = data_dir / WORK_DIR

    def status(text: str) -> None:
        if on_status is not None:
            on_status(text)

    def run(argv: Sequence[str], cwd: Path | None, timeout: float, *, git: bool = False) -> RunResult:
        env = git_env() if git else None
        return runner(tuple(argv), cwd=cwd, timeout_s=timeout, log_path=log_path, env=env)

    status("Update: checking dev")
    try:
        prepared = _ensure_clone(src, settings.repo_url, toolchain.git, run)
    except _Stop as stop:
        _record(data_dir, PHASE_FAILED, stop.message, installed_commit, "")
        return _done(PHASE_FAILED, stop.message, installed_commit, "")
    if not prepared:
        _record(data_dir, PHASE_FAILED, "source clone is not ready", installed_commit, "")
        return _done(PHASE_FAILED, "source clone is not ready", installed_commit, "")

    git = toolchain.git
    upstream, why = fetch_dev(git, src, run)
    if why:
        _record(data_dir, PHASE_FAILED, why, installed_commit, "")
        return _done(PHASE_FAILED, why, installed_commit, "")

    relation, ancestor_ran = _relation(git, src, installed_commit, upstream, run)
    if relation == SAME:
        _record(data_dir, PHASE_CURRENT, "Already on dev", installed_commit, upstream)
        status("Update: up to date")
        return _done(PHASE_CURRENT, "Already on dev", installed_commit, upstream)
    if relation != NEWER:
        message = "dev is not a fast-forward of the installed commit" if ancestor_ran else "could not compare commits"
        _record(data_dir, PHASE_FAILED, message, installed_commit, upstream)
        return _done(PHASE_FAILED, message, installed_commit, upstream)

    status("Update: pulling")
    pull = run(
        (git, "-C", str(src), "pull", "--ff-only", "origin", CHANNEL),
        src,
        PULL_TIMEOUT_S,
        git=True,
    )
    if pull.code != 0:
        _record(data_dir, PHASE_FAILED, "git pull --ff-only failed", installed_commit, upstream)
        return _done(PHASE_FAILED, "git pull --ff-only failed", installed_commit, upstream)

    head = run((git, "-C", str(src), "rev-parse", "HEAD"), src, PROBE_TIMEOUT_S, git=True)
    built_commit = _hash_line(head.output) if head.code == 0 else upstream

    python = toolchain.python
    status("Update: selftest")
    selftest = run((*python, "overlay.py", "--selftest"), src, CHECK_TIMEOUT_S)
    if selftest.code != 0:
        _record(data_dir, PHASE_FAILED, "selftest failed", installed_commit, upstream)
        return _done(PHASE_FAILED, "selftest failed", installed_commit, upstream)

    status("Update: boot check")
    boot = run((*python, "overlay.py", "--bootcheck-only"), src, CHECK_TIMEOUT_S)
    if boot.code != 0:
        _record(data_dir, PHASE_FAILED, "boot check failed", installed_commit, upstream)
        return _done(PHASE_FAILED, "boot check failed", installed_commit, upstream)

    status("Update: building")
    try:
        staging = _build(src, work, data_dir, install_dir, python, built_commit, run)
    except _Stop as stop:
        _record(data_dir, PHASE_FAILED, stop.message, installed_commit, upstream)
        return _done(PHASE_FAILED, stop.message, installed_commit, upstream)

    helper = (
        *python,
        "-m",
        "cli_avatars.update.helper",
        "--install",
        str(install_dir),
        "--staging",
        str(staging),
        "--log",
        str(log_path),
        "--data",
        str(data_dir),
        "--exe",
        EXE_NAME,
    )
    _record(data_dir, PHASE_STAGED, "Restarting onto the new build", installed_commit, upstream)
    status("Update: restarting")
    return UpdateResult(
        PHASE_STAGED,
        "Restarting onto the new build",
        installed_commit,
        upstream,
        staging,
        helper,
        src,
    )


def fetch_dev(git: str, src: Path, run: Callable) -> tuple[str, str]:
    """``git fetch origin dev``, then ``origin/dev``'s hash: ``(hash, "")``, or ``("", why)``."""
    fetch = run((git, "-C", str(src), "fetch", "origin", CHANNEL), src, FETCH_TIMEOUT_S, git=True)
    if fetch.code != 0:
        return "", "git fetch failed"
    rev = run((git, "-C", str(src), "rev-parse", f"origin/{CHANNEL}"), src, PROBE_TIMEOUT_S, git=True)
    upstream = _hash_line(rev.output) if rev.code == 0 else ""
    return (upstream, "") if upstream else ("", "could not read origin/dev")


def read_state(data_dir: Path) -> dict:
    """Last update record. Unknown files yield an empty dict. No paths are required."""
    path = data_dir / STATE_NAME
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    kept = {}
    for key in ("last_checked", "phase", "message", "commit", "upstream", "channel"):
        value = data.get(key)
        if isinstance(value, str):
            kept[key] = value
    return kept


class _Stop(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _done(phase: str, message: str, installed: str, upstream: str) -> UpdateResult:
    return UpdateResult(phase, message, installed, upstream, None, (), None)


def _record(data_dir: Path, phase: str, message: str, installed: str, upstream: str) -> None:
    path = data_dir / STATE_NAME
    if path.is_symlink():
        return
    payload = {
        "last_checked": stamp_now(),
        "phase": phase,
        "message": message[:200],
        "commit": short_commit(installed),
        "upstream": short_commit(upstream),
        "channel": CHANNEL,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _ensure_clone(src: Path, url: str, git: str, run: Callable) -> bool:
    if src.is_symlink():
        raise _Stop("source path is a symlink")
    git_dir = src / ".git"
    if git_dir.exists():
        remote = run((git, "-C", str(src), "remote", "get-url", "origin"), src, PROBE_TIMEOUT_S, git=True)
        if remote.code != 0:
            raise _Stop("could not read the source clone remote")
        if not _same_remote(remote.output, url):
            raise _Stop("source clone remote does not match the configured URL")
        return True
    if src.exists() and any(src.iterdir()):
        raise _Stop("source directory exists and is not a git clone")
    src.parent.mkdir(parents=True, exist_ok=True)
    cloned = run(
        (git, "clone", "--branch", CHANNEL, "--single-branch", "--", url, str(src)),
        src.parent,
        PULL_TIMEOUT_S,
        git=True,
    )
    if cloned.code != 0 or not git_dir.exists():
        raise _Stop("git clone failed")
    return True


def _relation(git: str, src: Path, installed: str, upstream: str, run: Callable) -> tuple[str, bool]:
    if same_commit(installed, upstream):
        return SAME, False
    if not installed:
        return NEWER, False
    probe = run(
        (git, "-C", str(src), "merge-base", "--is-ancestor", installed, f"origin/{CHANNEL}"),
        src,
        PROBE_TIMEOUT_S,
        git=True,
    )
    if probe.code == 0:
        ancestor: bool | None = True
    elif probe.code == 1:
        ancestor = False
    else:
        ancestor = None
    return commit_relation(installed, upstream, ancestor=ancestor), probe.code in (0, 1)


def _build(
    src: Path,
    work: Path,
    data_dir: Path,
    install_dir: Path,
    python: tuple[str, ...],
    commit: str,
    run: Callable,
) -> Path:
    _reset_work(work, data_dir)
    dist = work / "dist"
    build = work / "work"
    dist.mkdir(parents=True)
    build.mkdir(parents=True)
    spec = src / "packaging" / "cli_avatars.spec"
    if not spec.is_file():
        raise _Stop("packaging spec is missing from the source clone")
    built = run(
        (
            *python,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist),
            "--workpath",
            str(build),
            str(spec),
        ),
        src,
        BUILD_TIMEOUT_S,
    )
    if built.code != 0:
        raise _Stop("PyInstaller failed")
    folder = dist / COLLECT_NAME
    exe = folder / EXE_NAME
    if not folder.is_dir() or not exe.is_file():
        raise _Stop("build did not produce the app folder")
    write_stamp(folder / STAMP_NAME, version_in_tree(src), commit)
    staging = install_dir.with_name(install_dir.name + ".staging")
    if staging.is_symlink() or install_dir.is_symlink():
        raise _Stop("refusing to stage through a symlink")
    if staging.parent.resolve() != install_dir.parent.resolve():
        raise _Stop("staging is not beside the install directory")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.move(str(folder), str(staging))
    return staging


def _reset_work(work: Path, data_dir: Path) -> None:
    if work.name != WORK_DIR or work.parent.resolve() != data_dir.resolve():
        raise _Stop("refusing to clear this directory")
    if work.is_symlink():
        raise _Stop("update work path is a symlink")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)


def _overlap_reason(install_dir: Path, data_dir: Path) -> str:
    try:
        install = install_dir.resolve()
        data = data_dir.resolve()
    except OSError:
        return "install directory is not usable"
    if install == data or _is_inside(install, data) or _is_inside(data, install):
        return "install directory overlaps app data"
    src = data / SRC_DIR
    if _is_inside(install, src) or _is_inside(src, install):
        return "install directory overlaps the source clone"
    return ""


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return path.resolve() != parent.resolve()


def _hash_line(output: str) -> str:
    line = output.strip().splitlines()
    if not line:
        return ""
    return _hex(line[0].strip())


def _same_remote(output: str, expected: str) -> bool:
    line = ""
    for row in output.splitlines():
        if row.strip():
            line = row.strip()
            break
    return _norm_url(line) == _norm_url(expected) and _norm_url(expected) != ""


def _norm_url(url: str) -> str:
    text = url.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text.lower()
