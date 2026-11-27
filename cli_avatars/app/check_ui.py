"""CHECK-UPD.1: Check for updates on the toolbar, in Settings, the tray and the phone. It only looks.

``start_check`` fetches dev (``check_dev``) on a worker and says "up to date" or "N new on dev" with the newest
subjects on the status bar and in Settings; the Update buttons get an ember badge with the count. Check and Update
share Update's running gate, so they never run at once. Only a missing git disables it: a source checkout checks
itself. The update bar shows the fetch phase alone.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime

import text_fonts as fonts
from cli_avatars.app import update_ui
from cli_avatars.paths import REPO_ROOT
from cli_avatars.update import progress
from cli_avatars.update.check import PHASE_CURRENT, PHASE_FAILED, PHASE_NEWS, CheckResult, check_dev
from cli_avatars.update.config import update_config
from cli_avatars.update.version import running_commit
from events import app_data_dir

_BG = "#0d0d1a"
_FG = "#aaccff"
_SEL = "#223366"
_DIM = "#9a98b8"
_BAD = "#ff8866"
_OK = "#44ff88"
_NEWS = "#ffb060"
EMBER, EMBER_INK, EMBER_EDGE = "#ff7a1e", "#170b04", "#a8340e"


def check_block(app) -> str:
    """Why Check cannot run: the tools are still being probed, or git is missing. PyInstaller does not matter."""
    toolchain = getattr(app, "_update_toolchain", None)
    if toolchain is None:
        return "Checking git and PyInstaller"
    if not toolchain.git:
        return "git is not on PATH"
    return ""


def start_check(app) -> str:
    """Toolbar, Settings, tray and phone entry. Returns why it did not start, also shown on the status bar."""
    if getattr(app, "_check_running", False):
        why = "Check: already running"
    elif getattr(app, "_update_running", False):
        why = "Check: an update is running"
    else:
        why = check_block(app)
    if why:
        update_ui._set_status(app, why)
        return why
    app._check_running = True
    app._bar_owner = "check"
    update_ui.sync_update_tool(app)
    _refresh(app)
    update_ui._set_status(app, "Check: checking dev")
    install = update_ui.installed_dir()
    git = app._update_toolchain.git
    threading.Thread(target=_worker, args=(app, install, git), name="cli-avatars-check", daemon=True).start()
    return ""


def _worker(app, install, git: str) -> None:
    try:
        result = check_dev(
            data_dir=app_data_dir(),
            install_dir=install,
            source_root=REPO_ROOT,
            settings=update_config(getattr(app, "config", {})),
            installed_commit=running_commit(install),
            git=git,
            runner=update_ui._runner(),
            on_status=lambda text: update_ui._later(app, lambda text=text: update_ui._set_status(app, text)),
        )
    except Exception:
        result = CheckResult(PHASE_FAILED, "check failed")
    update_ui._later(app, lambda result=result: _finish(app, result))


def _finish(app, result: CheckResult) -> None:
    app._check_running = False
    app._check = result
    app._check_at = datetime.now().strftime("%H:%M")
    if result.phase in (PHASE_CURRENT, PHASE_NEWS):
        app._check_behind = result.behind
    update_ui._set_status(app, line(app))
    update_ui.sync_update_tool(app)
    _refresh(app)
    if result.phase == PHASE_NEWS:
        from cli_avatars.app.chime_cues import cue

        cue(app, "found")


def clear(app) -> None:
    """Update found dev current: no badge."""
    app._check_behind = 0
    sync_check_tool(app)


def badge_count(app) -> int:
    return int(getattr(app, "_check_behind", 0) or 0)


def line(app) -> str:
    """The status-bar line for the last check."""
    result = getattr(app, "_check", None)
    if result is None:
        return ""
    at = getattr(app, "_check_at", "")
    if result.phase == PHASE_CURRENT:
        return f"Check: up to date · checked {at}"
    if result.phase == PHASE_NEWS:
        return f"Check: {result.message} · checked {at}"
    return "Check: " + result.message


def bar(app) -> progress.Bar:
    result = getattr(app, "_check", None)
    phase = "" if result is None or getattr(app, "_check_running", False) else result.phase
    return progress.check_bar(getattr(app, "_update_line", ""), phase, bool(getattr(app, "_check_running", False)))


def sync_check_tool(app) -> None:
    """Toolbar Check: enabled unless git is missing or a run is under way; the ember badges follow the count."""
    reason = check_block(app)
    if not reason and getattr(app, "_check_running", False):
        reason = "Check: already running"
    if not reason and getattr(app, "_update_running", False):
        reason = "Check: an update is running"
    button = getattr(app, "_check_tool", None)
    if button is not None:
        try:
            button.config(state="disabled" if reason else "normal", cursor="" if reason else "hand2")
            button._kit_reason = reason
        except tk.TclError:
            pass
    for widget in (getattr(app, "_update_tool", None), getattr(app, "_update_button", None)):
        _badge(widget, badge_count(app))


def fill_settings(app, frame, row) -> None:
    """Check for updates beside Update app in ``row``, and the last result under the bar."""
    busy = check_block(app) or getattr(app, "_check_running", False) or getattr(app, "_update_running", False)
    button = tk.Button(
        row, text="Check for updates", command=lambda: start_check(app),
        bg=_SEL, fg=_FG, activebackground="#334477", activeforeground="white",
        font=fonts.face(9, "bold"), relief="flat", padx=10, pady=4, cursor="hand2",
    )
    button.pack(side="left", padx=(8, 0))
    if busy:
        button.config(state="disabled", cursor="")
    app._check_button = button
    result = getattr(app, "_check", None)
    if result is not None and not getattr(app, "_check_running", False):
        at = getattr(app, "_check_at", "")
        text, color = {
            PHASE_CURRENT: (f"Check: up to date · {at}", _OK),
            PHASE_NEWS: (f"Check: {result.message} · {at}", _NEWS),
        }.get(result.phase, ("Check stopped: " + result.message, _BAD))
        update_ui.wrap(tk.Label(frame, text=text, bg=_BG, fg=color, font=fonts.face(9, "bold"),
                                anchor="w")).pack(fill="x", padx=(10, 4))
        for subject in result.subjects if result.phase == PHASE_NEWS else ():
            update_ui.wrap(tk.Label(frame, text="· " + subject, bg=_BG, fg=_DIM, font=fonts.face(9),
                                    anchor="w")).pack(fill="x", padx=(20, 4))
    sync_check_tool(app)


def phone_status(app) -> dict:
    """The phone's Check row: may it run, why not, and the last result."""
    result = getattr(app, "_check", None)
    running = bool(getattr(app, "_check_running", False))
    reason = check_block(app)
    return {"enabled": not reason and not running and not getattr(app, "_update_running", False), "reason": reason,
            "running": running, "phase": "" if result is None else result.phase,
            "note": "" if result is None else result.message, "behind": badge_count(app),
            "subjects": [] if result is None else list(result.subjects), "at": getattr(app, "_check_at", "")}


def _refresh(app) -> None:
    refresh = getattr(app, "_refresh_update_panel", None)
    if refresh is not None:
        refresh()


def _badge(widget, count: int) -> None:
    """A small ember plate with the count over the button's top-right corner, clear of its label; gone at zero."""
    if widget is None:
        return
    try:
        if not widget.winfo_exists():
            return
        badge = getattr(widget, "_check_badge", None)
        if badge is None or not badge.winfo_exists():
            badge = tk.Label(widget.master, bg=EMBER, fg=EMBER_INK, font=fonts.face(8, "bold"), padx=2, pady=0,
                             bd=0, highlightthickness=1, highlightbackground=EMBER_EDGE, cursor="hand2")
            badge.bind("<Button-1>", lambda _e: widget.invoke())
            widget._check_badge = badge
        if count <= 0:
            badge.place_forget()
            return
        badge.config(text=str(count) if count < 100 else "99+")
        badge.place(in_=widget, relx=1.0, x=6, y=-3, anchor="ne")
        badge.lift()
    except tk.TclError:
        return
