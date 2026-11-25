"""BG.1: the Dungeon `x` asks Close or Minimize. Minimize hides to the tray; the app keeps running.

The picker is a parchment panel inside the Dungeon, not a new window. Without a tray icon,
Minimize iconifies to the taskbar so the window can always come back.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from dataclasses import replace

from cli_avatars.app.config_file import save_config_with
from cli_avatars.app.tasks_card import EDGE, GOLD, INK, PAPER, PARCH, SOFT, WINE, WOOD, button
from cli_avatars.desktop.settings import desktop_settings, with_on_close

LABELS = {"ask": "Ask", "minimize": "Minimize to tray", "quit": "Quit"}
NOTICE = "The Dungeon is still running. Click the tray icon to open it again."


def request_close(app) -> None:
    """``WM_DELETE_WINDOW``: ask, minimize or quit per ``desktop.on_close``."""
    choice = desktop_settings(getattr(app, "config", {})).on_close
    if choice == "quit":
        app._quit()
    elif choice == "minimize":
        minimize(app)
    elif picker(app) is None:
        app._close_picker = Picker(app)
    else:
        app._close_picker.focus_set()


def quit_app(app) -> None:
    """Hide every window first, then stop each part. A failing part never blocks the rest or the exit."""
    if getattr(app, "_quitting", False):
        return
    app._quitting = True
    _hide_all(app.root)
    chat = sys.modules.get("chat_window")
    steps = (
        getattr(getattr(app, "places", None), "save_now", None),
        getattr(getattr(app, "dungeon", None), "save_now", None),
        getattr(getattr(getattr(app, "scanner", None), "_events", None), "close", None),
        getattr(getattr(app, "_tray", None), "stop", None),
        getattr(chat, "stop_runs_on_quit", None),
    )
    for step in steps:
        try:
            if step:
                step()
        except Exception:
            logging.getLogger("cli_avatars.quit").exception("quit step failed")
    app.root.quit()


def _hide_all(widget) -> None:
    for child in widget.winfo_children():
        _hide_all(child)
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        try:
            widget.withdraw()
        except tk.TclError:
            pass


def picker(app):
    panel = getattr(app, "_close_picker", None)
    try:
        return panel if panel is not None and panel.winfo_exists() else None
    except tk.TclError:
        return None


def tray_ready(app) -> bool:
    return bool(getattr(getattr(app, "_tray", None), "visible", False))


def minimize(app) -> None:
    """Hide to the tray, or iconify to the taskbar when there is no tray icon."""
    root = app.root
    if not tray_ready(app):
        root.iconify()
        return
    app._close_rect = (root.state(), root.geometry())
    pop = getattr(getattr(app, "dungeon", None), "_pop", None)
    if pop is not None:
        pop.withdraw()
    root.withdraw()
    if not getattr(app, "_close_noticed", False):
        app._close_noticed = True
        try:
            app._tray.notify(NOTICE, "Dungeon")
        except Exception:
            pass


def restore(app) -> None:
    """Put back the rect the window had when it went to the tray. The caller raises it."""
    saved = getattr(app, "_close_rect", None)
    app._close_rect = None
    if saved is None:
        return
    state, geometry = saved
    try:
        if state == "zoomed":
            app.root.state("zoomed")
        else:
            app.root.geometry(geometry)
    except tk.TclError:
        pass


def set_choice(app, choice: str) -> None:
    """Remember what the `x` does, in memory and in config.json."""
    app.config = with_on_close(getattr(app, "config", {}), choice)
    path = getattr(app, "_config_path", None)
    if path is not None:
        save_config_with(path, lambda parsed: with_on_close(parsed, choice))
    desktop = getattr(app, "desktop", None)
    if desktop is not None:
        try:
            app.desktop = replace(desktop, on_close=choice)
        except TypeError:
            pass
    var = getattr(app, "_on_close_var", None)
    if var is not None and var.get() != LABELS[choice]:
        var.set(LABELS[choice])


def mount_setting(app, parent) -> tk.StringVar:
    """Settings row "When I close the window: Ask / Minimize to tray / Quit"."""
    bg, fg, sel, font = "#0d0d1a", "#aaccff", "#223366", ("Courier", 9)
    current = desktop_settings(getattr(app, "config", {})).on_close
    var = tk.StringVar(parent, LABELS[current])
    app._on_close_var = var
    by_label = {label: key for key, label in LABELS.items()}

    def _save(*_args):
        choice = by_label.get(var.get())
        if choice is not None and choice != desktop_settings(getattr(app, "config", {})).on_close:
            set_choice(app, choice)

    var.trace_add("write", _save)
    row = tk.Frame(parent, bg=bg, pady=3)
    row.pack(fill="x", padx=12)
    tk.Label(row, text="When I close", bg=bg, fg=fg, font=font, width=18, anchor="w").pack(side="left")
    menu = tk.OptionMenu(row, var, *LABELS.values())
    menu.config(bg=sel, fg=fg, activebackground="#334477", activeforeground="white", font=font,
                highlightthickness=0, bd=0)
    menu["menu"].config(bg=sel, fg=fg, font=font)
    menu.pack(side="left")
    return var


class Picker(tk.Frame):
    """Modal parchment panel centred on the Dungeon. Enter = Minimize, Esc = cancel."""

    def __init__(self, app) -> None:
        super().__init__(app.root, bg=WOOD)
        self.app = app
        self.remember = tk.BooleanVar(self, False)
        sheet = tk.Frame(self, bg=PARCH, highlightthickness=2, highlightbackground=EDGE)
        sheet.pack(padx=4, pady=4)
        head = tk.Frame(sheet, bg=WINE)
        head.pack(fill="x")
        tk.Label(head, text="Leaving the Dungeon?", bg=WINE, fg=PAPER, font="DungeonTitle").pack(
            side="left", padx=10, pady=4)
        where = "in the tray, by the clock" if tray_ready(app) else "on the taskbar"
        tk.Label(sheet, text=f"Minimize keeps your agents working.\nThe Dungeon waits {where}.",
                 bg=PARCH, fg=INK, font="DungeonText", justify="left").pack(anchor="w", padx=12, pady=(8, 4))
        tk.Checkbutton(sheet, text="Remember my choice (change it in Settings)", variable=self.remember,
                       bg=PARCH, fg=SOFT, activebackground=PARCH, selectcolor=PAPER, font="DungeonBubble",
                       highlightthickness=0, bd=0).pack(anchor="w", padx=10)
        row = tk.Frame(sheet, bg=PARCH)
        row.pack(fill="x", padx=12, pady=(8, 10))
        button(row, "Minimize", lambda: self.choose("minimize"), bg=GOLD, fg=INK).pack(side="left")
        button(row, "Close", lambda: self.choose("quit")).pack(side="left", padx=(8, 0))
        tk.Label(row, text="Enter  Esc", bg=PARCH, fg=SOFT, font="DungeonBubble").pack(side="right")
        self.bind("<Return>", lambda _e: self._key("minimize"))
        self.bind("<KP_Enter>", lambda _e: self._key("minimize"))
        self.bind("<Escape>", lambda _e: self._key(None))
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.lift()
        self.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _key(self, choice):
        if choice is None:
            self.close()
        else:
            self.choose(choice)
        return "break"

    def choose(self, choice: str) -> None:
        remember = bool(self.remember.get())
        self.close()
        if remember:
            set_choice(self.app, choice)
        if choice == "quit":
            self.app._quit()
        else:
            minimize(self.app)

    def close(self) -> None:
        try:
            self.grab_release()
            self.destroy()
        except tk.TclError:
            pass
        self.app._close_picker = None
