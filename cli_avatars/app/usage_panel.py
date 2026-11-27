"""USAGE.1: the Usage list under the Sessions panel: each session and bridged bot with its reported model, effort,
tokens, estimated cost and run time, then the total. Re-read every 2 s when ``usage.json`` or the bridge changed.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from cli_avatars.app import usage

BG = "#141018"
ROW = "#1c1626"
INK = "#e8e6f4"
DIM = "#9a98b8"
GOLD = "#ffcf4a"
TICK_MS = 2000
LIMIT = 12


class UsageList:
    def __init__(self, app, parent) -> None:
        self.app = app
        self._key = None
        self.frame = tk.Frame(parent, bg=BG)
        tk.Label(self.frame, text="  Usage", bg="#111018", fg="#88aaff", font="DungeonTitle",
                 anchor="w").pack(fill="x")
        self.rows = tk.Frame(self.frame, bg=BG)
        self.rows.pack(fill="x", padx=6, pady=(2, 6))
        self.refresh()

    def _directory(self) -> Path | None:
        directory = getattr(self.app, "_chat_directory", None)
        return Path(directory()) if callable(directory) else None

    def _stamp(self, directory: Path, config: object) -> tuple:
        import bot_bridge

        try:
            mtime = (directory / usage.FILE).stat().st_mtime_ns
        except OSError:
            mtime = 0
        return mtime, bot_bridge.stamp(bot_bridge.root(directory, config))

    def refresh(self) -> None:
        directory, config = self._directory(), getattr(self.app, "config", None)
        if directory is not None:
            key = self._stamp(directory, config)
            if key != self._key:
                self._key = key
                self._fill(usage.rows(directory, config))
        try:
            self.frame.after(TICK_MS, self.refresh)
        except tk.TclError:
            return

    def _fill(self, found: list[dict]) -> None:
        for child in self.rows.winfo_children():
            child.destroy()
        if not found:
            _text(self.rows, "No runs yet: a session shows here after its first answer.", DIM)
            return
        for row in found[:LIMIT]:
            box = tk.Frame(self.rows, bg=ROW)
            box.pack(fill="x", pady=1)
            who = ("bot " if row["kind"] == "bot" else "") + row["name"]
            head = tk.Frame(box, bg=ROW)
            head.pack(fill="x")
            tk.Label(head, text=who, bg=ROW, fg=INK, font="DungeonText", anchor="w").pack(side="left", padx=(4, 2))
            tk.Label(head, text=usage.label(row), bg=ROW, fg=GOLD, font="DungeonText").pack(side="right", padx=4)
            _text(box, usage.line(row) + ("  (effort: flag sent)" if row.get("effort_from") == "flag" else ""), DIM,
                  ROW)
        total = usage.total(found)
        box = tk.Frame(self.rows, bg="#2a2038")
        box.pack(fill="x", pady=(3, 1))
        count = " · ".join(f"{total[k]} {k[:-1] if total[k] == 1 else k}" for k in ("sessions", "bots"))
        _text(box, f"Total · {count}", GOLD, "#2a2038")
        _text(box, usage.line(total), INK, "#2a2038")
        _text(self.rows, usage.note(), DIM)


def _text(parent, text: str, fg: str, bg: str = BG) -> None:
    tk.Label(parent, text=text, bg=bg, fg=fg, font="DungeonText", anchor="w", justify="left",
             wraplength=250).pack(fill="x", padx=4)


def mount(panel) -> UsageList:
    """Pack the list under the Sessions panel's rows."""
    found = UsageList(panel.app, panel.frame)
    found.frame.pack(fill="x")
    return found
