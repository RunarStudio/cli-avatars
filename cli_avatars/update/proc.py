"""Fixed-argv processes for the updater.

This is the only update module that starts a process. ``shell`` is always
false. Arguments are a list of strings the caller built. Chat text never
reaches this function. Git's own credential helper may run, because the
parent environment is passed through; this module does not read credential
files and does not put tokens on the command line.

Stdout and stderr are appended to the update log. Userinfo in an https URL
is stripped before it is written.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_USERINFO = re.compile(r"(https://)[^\s/@]+(?::[^\s/@]+)?@")
_OUTPUT_CAP = 8192
_LOG_CAP = 1_000_000


@dataclass(frozen=True)
class RunResult:
    """Exit code and a short copy of the output. The log has the same text."""

    code: int
    output: str


def redact(text: str) -> str:
    """Drop ``user`` and ``user:token`` from https URLs."""
    return _USERINFO.sub(r"\1", text)


def git_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for git. Existing credential helpers stay. No prompt, no new tokens."""
    env = dict(os.environ if base is None else base)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def check_argv(argv: Sequence[str]) -> None:
    """Reject anything that is not a list of ordinary strings."""
    if isinstance(argv, (str, bytes)) or not isinstance(argv, (list, tuple)) or not argv:
        raise ValueError("argv must be a list of strings")
    for item in argv:
        if not isinstance(item, str) or item == "" or "\x00" in item:
            raise ValueError("argv item must be a string")


def run_fixed(
    argv: Sequence[str],
    *,
    cwd: Path | None,
    timeout_s: float,
    log_path: Path,
    env: Mapping[str, str] | None = None,
) -> RunResult:
    """Run ``argv`` and append combined output to ``log_path``.

    A timeout kills the process and returns code 124. The log receives a
    short note. The returned output is capped; the log keeps a larger copy.
    """
    check_argv(argv)
    if timeout_s <= 0:
        raise ValueError("timeout must be positive")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    shown = " ".join(argv)
    header = f"\n---- {shown}\n"
    try:
        completed = subprocess.run(
            list(argv),
            cwd=None if cwd is None else str(cwd),
            timeout=float(timeout_s),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=None if env is None else dict(env),
            check=False,
            **_windowless(hide=True),
        )
        code = int(completed.returncode)
        raw = completed.stdout or b""
        note = f"\n---- exit {code}\n"
    except subprocess.TimeoutExpired as exc:
        code = 124
        raw = exc.stdout or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        note = f"\n---- timeout after {timeout_s:g}s\n"
    except OSError as exc:
        code = 127
        raw = str(exc).encode("utf-8", "replace")
        note = "\n---- exit 127\n"
    text = redact(raw.decode("utf-8", "replace"))
    _append(log_path, redact(header + _clip(text, _LOG_CAP) + note))
    return RunResult(code, _clip(text, _OUTPUT_CAP))


def spawn_detached(argv: Sequence[str], *, cwd: Path | None) -> None:
    """Start ``argv`` and return. The child survives the parent exiting."""
    check_argv(argv)
    kwargs: dict = {
        "args": list(argv),
        "cwd": None if cwd is None else str(cwd),
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs.update(_windowless(hide=False))
        kwargs["creationflags"] |= subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(**kwargs)


def _windowless(*, hide: bool) -> dict:
    """Windows kwargs: a console child gets a hidden console; ``hide`` also hides its first window."""
    if sys.platform != "win32":
        return {}
    # Not DETACHED_PROCESS: Windows then ignores CREATE_NO_WINDOW and a console grandchild opens a window.
    kwargs: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
    if hide:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = info
    return kwargs


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n---- output truncated\n"


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
