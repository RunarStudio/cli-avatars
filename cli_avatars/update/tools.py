"""Find git and a Python that can run PyInstaller.

The frozen app is not a Python interpreter, so a packaged build looks for
``py -3`` or ``python`` on ``PATH``. The check is ``python -m PyInstaller
--version``. A missing tool becomes a short reason the Settings button shows.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from cli_avatars.update.machine import PROBE_TIMEOUT_S, Toolchain
from cli_avatars.update.proc import run_fixed


def block_reason(tools_reason: str, installed: bool) -> str:
    """Why Update app cannot run. Empty means the button may be enabled."""
    if tools_reason:
        return tools_reason
    if not installed:
        return "Running from source. Install CLI Avatars to update it."
    return ""


def probe_tools(log_path: Path | None = None) -> Toolchain:
    """Look up git and PyInstaller. ``reason`` is empty when both can run."""
    git = shutil.which("git")
    python = find_python()
    reasons: list[str] = []
    if not git:
        reasons.append("git is not on PATH")
    pyinstaller = False
    if not python:
        reasons.append("Python is not on PATH, so PyInstaller cannot run")
    elif _pyinstaller_runs(python, log_path):
        pyinstaller = True
    else:
        reasons.append("PyInstaller is not installed (python -m PyInstaller --version failed)")
    return Toolchain(
        git=git,
        python=tuple(python or ()),
        pyinstaller=pyinstaller,
        reason="; ".join(reasons),
    )


def find_python() -> list[str] | None:
    """Interpreter used to run the source clone. Not the frozen executable."""
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    py = shutil.which("py")
    if py and sys.platform == "win32":
        return [py, "-3"]
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def _pyinstaller_runs(python: list[str], log_path: Path | None) -> bool:
    temporary = None
    target = log_path
    if target is None:
        temporary = tempfile.NamedTemporaryFile(prefix="cli-avatars-pyi-", suffix=".log", delete=False)
        temporary.close()
        target = Path(temporary.name)
    try:
        result = run_fixed(
            (*python, "-m", "PyInstaller", "--version"),
            cwd=None,
            timeout_s=PROBE_TIMEOUT_S,
            log_path=target,
        )
    except (OSError, ValueError):
        return False
    finally:
        if temporary is not None:
            try:
                target.unlink()
            except OSError:
                pass
    return result.code == 0
