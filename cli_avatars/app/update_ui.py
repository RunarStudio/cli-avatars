"""Update app in the Settings dock and on the status bar.

The button and the tray item call ``start_update``. Progress replaces the
status-bar text. No extra window is created. A missing git or PyInstaller
leaves the button disabled and names the reason.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

from cli_avatars.update.config import update_config
from cli_avatars.update.machine import (
    PHASE_CURRENT,
    PHASE_FAILED,
    PHASE_STAGED,
    UpdateResult,
    read_state,
    run_update,
)
from cli_avatars.update.proc import spawn_detached
from cli_avatars.update.tools import block_reason
from cli_avatars.update.version import display_version, frozen_install_dir, running_commit
from events import app_data_dir

_BG = "#0d0d1a"
_FG = "#aaccff"
_SEL = "#223366"
_DIM = "#9a98b8"
_BAD = "#ff8866"
_OK = "#44ff88"


def installed_dir() -> Path | None:
    """Directory of a frozen build. A source checkout has no install directory."""
    return frozen_install_dir()


def mount_update_status(app) -> None:
    """Status-bar label. Packed to the left so the boot check keeps the right side."""
    parent = getattr(app, "_status_parent", None)
    if parent is None:
        return
    label = tk.Label(parent, text="", bg="#111018", fg=_DIM, font=("Courier", 10), anchor="w")
    label.pack(side="left", padx=(10, 4))
    app._update_label = label


def mount_update_settings(app, win) -> None:
    """Version, commit, last checked, and the Update app button. Not a new window."""
    frame = tk.Frame(win, bg=_BG)
    frame.pack(fill="x", padx=8, pady=(8, 0))
    app._update_panel = frame
    app._refresh_update_panel = lambda: _fill(app)
    _fill(app)


def apply_probe(app, toolchain) -> None:
    """Store the tool probe and refresh the dock if it is already open."""
    app._update_toolchain = toolchain
    app._update_block = block_reason(toolchain.reason, installed_dir() is not None)
    sync_update_tool(app)
    refresh = getattr(app, "_refresh_update_panel", None)
    if refresh is not None:
        refresh()


def sync_update_tool(app) -> None:
    """Toolbar Update: enabled when the update may run, else disabled with the reason as tooltip."""
    button = getattr(app, "_update_tool", None)
    if button is None:
        return
    reason = getattr(app, "_update_block", "Checking git and PyInstaller")
    if not reason and getattr(app, "_update_running", False):
        reason = "Update: already running"
    try:
        button.config(state="disabled" if reason else "normal", cursor="" if reason else "hand2")
    except tk.TclError:
        return
    button._kit_reason = reason


def start_update(app) -> None:
    """Tray and Settings entry. Disabled reasons are shown on the status bar."""
    if getattr(app, "_update_running", False):
        _set_status(app, "Update: already running")
        return
    reason = getattr(app, "_update_block", "Checking git and PyInstaller")
    if reason:
        _set_status(app, reason)
        return
    install = installed_dir()
    toolchain = getattr(app, "_update_toolchain", None)
    if install is None or toolchain is None:
        _set_status(app, "Running from source. Install CLI Avatars to update it.")
        return
    app._update_running = True
    _set_button(app, enabled=False)
    _set_status(app, "Update: checking dev")
    threading.Thread(target=_worker, args=(app, install, toolchain), name="cli-avatars-update", daemon=True).start()


def _worker(app, install: Path, toolchain) -> None:
    directory = app_data_dir()
    installed = running_commit(install)
    try:
        result = run_update(
            data_dir=directory,
            install_dir=install,
            settings=update_config(getattr(app, "config", {})),
            installed_commit=installed,
            toolchain=toolchain,
            runner=_runner(),
            on_status=lambda text: _later(app, lambda text=text: _set_status(app, text)),
        )
    except Exception:
        result = UpdateResult(PHASE_FAILED, "update failed", installed, "", None, (), None)
    _later(app, lambda result=result: _finish(app, result))


def _finish(app, result: UpdateResult) -> None:
    app._update_running = False
    _set_status(app, _bar(result))
    refresh = getattr(app, "_refresh_update_panel", None)
    if refresh is not None:
        refresh()
    if result.phase != PHASE_STAGED or not result.helper_argv or result.helper_cwd is None:
        _set_button(app, enabled=not getattr(app, "_update_block", ""))
        return
    try:
        spawn_detached(result.helper_argv, cwd=result.helper_cwd)
    except (OSError, ValueError):
        _set_status(app, "Update: could not start the restart helper")
        _set_button(app, enabled=not getattr(app, "_update_block", ""))
        return
    quit_app = getattr(app, "_quit", None)
    if quit_app is not None:
        quit_app()


def _fill(app) -> None:
    frame = getattr(app, "_update_panel", None)
    if frame is None:
        return
    try:
        if not frame.winfo_exists():
            return
    except tk.TclError:
        return
    for child in list(frame.winfo_children()):
        child.destroy()
    install = installed_dir()
    version, commit = display_version(install)
    state = {}
    try:
        state = read_state(app_data_dir())
    except OSError:
        state = {}
    checked = state.get("last_checked") or "not yet"
    tk.Label(
        frame, text=f"  {version}  ·  {commit or 'no commit'}  ·  dev",
        bg=_BG, fg=_FG, font=("Courier", 10, "bold"), anchor="w",
    ).pack(fill="x")
    tk.Label(
        frame, text=f"  Last checked  {checked}",
        bg=_BG, fg=_DIM, font=("Courier", 9), anchor="w",
    ).pack(fill="x", pady=(2, 4))
    reason = getattr(app, "_update_block", "Checking git and PyInstaller")
    running = bool(getattr(app, "_update_running", False))
    button = tk.Button(
        frame, text="Update app", command=lambda: start_update(app),
        bg=_SEL, fg=_FG, activebackground="#334477", activeforeground="white",
        font=("Courier", 9, "bold"), relief="flat", padx=10, pady=4, cursor="hand2",
    )
    button.pack(anchor="w", padx=8, pady=(0, 4))
    if reason or running:
        button.config(state="disabled", cursor="")
    if reason:
        tk.Label(frame, text="  " + reason, bg=_BG, fg=_BAD, font=("Courier", 9), anchor="w").pack(fill="x")
    app._update_button = button


def _bar(result: UpdateResult) -> str:
    if result.phase == PHASE_CURRENT:
        return "Update: up to date"
    if result.phase == PHASE_STAGED:
        return "Update: restarting"
    if result.phase == PHASE_FAILED:
        return "Update: " + result.message
    return result.message


def _set_status(app, text: str) -> None:
    label = getattr(app, "_update_label", None)
    if label is None:
        return
    try:
        label.config(text=text, fg=_OK if "up to date" in text else _FG)
    except tk.TclError:
        return


def _set_button(app, enabled: bool) -> None:
    sync_update_tool(app)
    button = getattr(app, "_update_button", None)
    if button is None:
        return
    try:
        button.config(state="normal" if enabled else "disabled")
    except tk.TclError:
        return


def _later(app, fn) -> None:
    root = getattr(app, "root", None)
    if root is None:
        return
    try:
        root.after(0, fn)
    except tk.TclError:
        return


def _runner():
    from cli_avatars.update.proc import run_fixed

    return run_fixed
