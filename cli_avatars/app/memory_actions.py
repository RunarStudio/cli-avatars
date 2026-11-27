"""MEMORY.1: Consolidate now, Open in Obsidian and the scheduler line. No Tk.

The app never edits a note: Consolidate now drops ``_app/consolidate.request`` and starts the curator script
(``_app/memory_curator.py``) with a fixed argv; the curator does the rest and writes ``_app/status.json``.
"""

from __future__ import annotations

import shutil
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

from cli_avatars.app import memory_notes as mn

TASK_NAME = "CLI Avatars memory curator"


def consolidate_at(config: object) -> str:
    """``memory.consolidate_at`` as ``HH:MM`` (default 03:00)."""
    raw = mn.setting(config, "consolidate_at", "03:00")
    try:
        return time.strftime("%H:%M", time.strptime(raw.strip(), "%H:%M"))
    except ValueError:
        return "03:00"


def python_binary() -> str:
    """This interpreter from source; the one on PATH from the packaged app; ``""`` with none."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in ("pythonw", "python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def scheduler_lines(root: Path, at: str, python: str = "") -> dict[str, str]:
    """Paste-ready lines that run the curator daily at ``at``: Windows Task Scheduler and cron."""
    python = python or python_binary() or "python"
    script = Path(root) / mn.CURATOR
    hour, minute = at.split(":")
    windows = (f'schtasks /Create /F /SC DAILY /ST {at} /TN "{TASK_NAME}" '
               f'/TR "\\"{python}\\" \\"{script}\\" --root \\"{root}\\""')
    cron = f'{int(minute)} {int(hour)} * * * "{python}" "{script}" --root "{root}"'
    return {"windows": windows, "cron": cron}


def consolidate_now(root: Path, start=None) -> str:
    """Ask the curator to run: the request file, then the script started; the line to show."""
    root = Path(root)
    if not mn.exists(root):
        return "Set up the notes folder first (Settings > Memory > Create)."
    script = root / mn.CURATOR
    try:
        (root / mn.REQUEST).write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    except OSError as error:
        return f"Could not ask the curator: {error.strerror or error}"
    python = python_binary()
    if not script.is_file() or not python:
        return "Asked. The curator runs at its scheduled time (no Python found to start it now)."
    if start is None:
        from chat_window import start_curator as start
    return "Consolidating…" if start(python, script, root) else "Asked. The curator could not start now."


def obsidian_url(path: Path) -> str:
    return "obsidian://open?path=" + quote(str(path), safe="")


def open_in_obsidian(path: Path, opener=webbrowser.open) -> bool:
    try:
        return bool(opener(obsidian_url(path)))
    except Exception:
        return False
