"""CHECK-UPD.1: Check for updates. Fetch ``dev`` and count what is new; nothing is pulled, built or restarted.

An installed build checks its clone in the data dir (the one Update pulls); a source checkout checks itself. The
fetch is Update's own step (``fetch_dev``). Commands are fixed argument lists through the same runner as Update.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cli_avatars.bootcheck import stamp_now
from cli_avatars.update.config import CHANNEL, UpdateConfig, normalize_repo_url
from cli_avatars.update.machine import (
    LOG_NAME,
    PHASE_BLOCKED,
    PHASE_CURRENT,
    PHASE_FAILED,
    PROBE_TIMEOUT_S,
    SRC_DIR,
    STATE_NAME,
    Runner,
    StatusFn,
    _ensure_clone,
    _Stop,
    fetch_dev,
)
from cli_avatars.update.proc import RunResult, git_env
from cli_avatars.update.version import _hex

PHASE_NEWS = "updates"
MAX_SUBJECTS = 5
SUBJECT_CAP = 120

__all__ = ["PHASE_BLOCKED", "PHASE_CURRENT", "PHASE_FAILED", "PHASE_NEWS", "CheckResult", "check_dev"]


@dataclass(frozen=True)
class CheckResult:
    """``phase`` is up_to_date, updates, failed or blocked; ``subjects`` are the newest first, at most five."""

    phase: str
    message: str
    behind: int = 0
    subjects: tuple[str, ...] = ()
    upstream: str = ""


def check_dev(
    *,
    data_dir: Path,
    install_dir: Path | None,
    source_root: Path,
    settings: UpdateConfig,
    installed_commit: str,
    git: str | None,
    runner: Runner,
    on_status: StatusFn | None = None,
) -> CheckResult:
    """One check. ``install_dir`` None means running from source: ``source_root`` is fetched."""
    if not git:
        return CheckResult(PHASE_BLOCKED, "git is not on PATH")
    if install_dir is not None and (settings.error or not normalize_repo_url(settings.repo_url)):
        return CheckResult(PHASE_BLOCKED, settings.error or "update settings are not usable")
    log_path = data_dir / LOG_NAME

    def run(argv: Sequence[str], cwd: Path | None, timeout: float, *, git: bool = False) -> RunResult:
        return runner(tuple(argv), cwd=cwd, timeout_s=timeout, log_path=log_path, env=git_env() if git else None)

    if on_status is not None:
        on_status("Check: checking dev")
    src = source_root
    if install_dir is not None:
        src = data_dir / SRC_DIR
        try:
            _ensure_clone(src, settings.repo_url, git, run)
        except _Stop as stop:
            return _checked(data_dir, CheckResult(PHASE_FAILED, stop.message))
    upstream, why = fetch_dev(git, src, run)
    if why:
        return _checked(data_dir, CheckResult(PHASE_FAILED, why))
    installed = _hex(installed_commit)
    if not installed:
        return _checked(data_dir, CheckResult(PHASE_FAILED, "no commit for the running build", upstream=upstream))
    span = f"{installed}..origin/{CHANNEL}"
    counted = run((git, "-C", str(src), "rev-list", "--count", span), src, PROBE_TIMEOUT_S, git=True)
    behind = counted.output.strip()
    if counted.code != 0 or not behind.isdigit():
        return _checked(data_dir, CheckResult(PHASE_FAILED, "could not compare commits", upstream=upstream))
    if int(behind) == 0:
        return _checked(data_dir, CheckResult(PHASE_CURRENT, "Up to date", upstream=upstream))
    logged = run((git, "-C", str(src), "log", f"-n{MAX_SUBJECTS}", "--format=%s", span), src, PROBE_TIMEOUT_S,
                 git=True)
    subjects = tuple(line.strip()[:SUBJECT_CAP] for line in logged.output.splitlines() if line.strip()) \
        if logged.code == 0 else ()
    count = int(behind)
    return _checked(data_dir, CheckResult(PHASE_NEWS, f"{count} new on {CHANNEL}", count, subjects[:MAX_SUBJECTS],
                                          upstream))


def _checked(data_dir: Path, result: CheckResult) -> CheckResult:
    """Stamp ``last_checked`` in the update record; Update's own phase and commits stay."""
    path = data_dir / STATE_NAME
    if path.is_symlink():
        return result
    data: dict = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        data = loaded if isinstance(loaded, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        data = {}
    data["last_checked"] = stamp_now()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return result

