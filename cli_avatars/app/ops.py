"""OPS.1: answer ``cli-avatars-emit app status|restart|update`` and the phone's Restart. No tkinter import.

Restart starts this same program again (fixed argv, ``--wait-pid``) and quits; the new process waits until
the old one is gone. Update is the toolbar's ``start_update``. Nothing here starts an AI CLI.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from cli_avatars.desktop.process import pid_alive
from cli_avatars.update.proc import spawn_detached
from cli_avatars.update.version import display_version
from events import app_data_dir

APP_JSON = "app.json"
APP_LOG = "app.log"
LOG_CAP = 256 * 1024
EXE_NAMES = ("cli-avatars.exe", "cli-avatars")
SOURCE_ROOT = Path(__file__).resolve().parents[2]
UPDATE_BUSY = "Update is running. Restart after it finishes."


def launch_argv() -> list[str]:
    """How this program starts: the installed exe, or Python with ``overlay.py`` from a clone."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(SOURCE_ROOT / "overlay.py")]


def write_app_json(directory: Path, argv: list[str]) -> None:
    """Record how to start the app, so ``app restart`` can start it when it is not running."""
    path = Path(directory) / APP_JSON
    path.write_text(json.dumps({"argv": list(argv)}), encoding="utf-8")


def log_line(directory: Path, text: str) -> None:
    """Append one stamped line to ``app.log``; at the cap the old file becomes ``app.log.1``."""
    path = Path(directory) / APP_LOG
    try:
        if path.exists() and path.stat().st_size > LOG_CAP:
            os.replace(path, path.with_name(APP_LOG + ".1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except OSError:
        pass


def log_crash(directory: Path, where: str, exc: BaseException) -> None:
    """A traceback in ``app.log`` so a crash at start has a place to read."""
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    log_line(directory, f"crash in {where}:\n" + "".join(lines))


def status(app, directory: Path | None = None) -> dict:
    """Running, pid, version, commit, uptime, phone on/off and writes on/off, update line, data dir."""
    from webui.config import web_settings

    version, commit = display_version()
    started = float(getattr(app, "_ops_started", time.time()))
    return {
        "running": True,
        "pid": os.getpid(),
        "version": version,
        "commit": commit,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "uptime_s": int(time.time() - started),
        "phone": {"on": getattr(app, "_phone_server", None) is not None,
                  "writes": web_settings(getattr(app, "config", {}) or {}).allow_writes},
        "update": {"running": bool(getattr(app, "_update_running", False)),
                   "line": str(getattr(app, "_update_line", "") or "")},
        "data_dir": str(directory or app_data_dir()),
    }


def restart(app, directory: Path | None = None, spawn=None) -> str:
    """Start a fresh copy that waits for this one, then quit. ``""`` when it goes, else why not."""
    if getattr(app, "_update_running", False):
        return UPDATE_BUSY
    directory = directory or app_data_dir()
    argv = launch_argv() + ["--wait-pid", str(os.getpid())]
    try:
        (spawn or spawn_detached)(argv, cwd=Path(argv[-3]).parent)
    except (OSError, ValueError):
        return "Could not start a new Dungeon. Nothing was stopped."
    log_line(directory, f"restart requested, pid {os.getpid()} quits")
    app.root.after(400, app._quit)
    return ""


def wait_for_exit(pid: int, timeout: float = 30.0) -> bool:
    """True once ``pid`` is gone, False when it is still there after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while pid_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


class Control:
    """The UDP listener's ``on_control``: runs each verb on the Tk thread through ``call``."""

    def __init__(self, app, directory: Path | None = None, call=None, start_update=None, spawn=None) -> None:
        self.app = app
        self.directory = directory or app_data_dir()
        self._call = call or (lambda fn: fn())
        self._start_update = start_update
        self._spawn = spawn

    def handle(self, verb: str) -> dict:
        try:
            if verb == "restart":
                why = self._call(lambda: restart(self.app, self.directory, self._spawn))
            elif verb == "update":
                why = self._call(lambda: self._update())
            else:
                why = ""
        except Exception:
            return {"ok": False, "why": "The Dungeon did not answer. Try again."}
        if verb != "status":
            log_line(self.directory, f"{verb} from the command line: {why or 'started'}")
        return {"ok": not why, "why": why, **status(self.app, self.directory)}

    def _update(self) -> str:
        start = self._start_update
        if start is None:
            from cli_avatars.app.update_ui import start_update as start
        return start(self.app) or ""


def attach(app, directory: Path | None = None) -> None:
    """At start: note the start time and argv, log it, and answer control requests on the event listener."""
    directory = directory or app_data_dir()
    app._ops_started = time.time()
    try:
        write_app_json(directory, launch_argv())
    except OSError:
        pass
    version, commit = display_version()
    log_line(directory, f"started pid {os.getpid()} version {version} commit {commit or 'none'}")
    listener = getattr(getattr(app, "scanner", None), "_events", None)
    if listener is None:
        log_line(directory, "control off: the event listener did not start (port in use?)")
        return
    from webui.writes import TkCalls

    calls = TkCalls(app.root)
    app._ops_calls = calls
    listener.on_control = Control(app, directory, call=calls).handle
