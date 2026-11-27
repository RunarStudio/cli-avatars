"""MEMORY.1: Settings > Memory: the notes folder (``memory.root``) with Create, the nightly time
(``memory.consolidate_at``), Topic rooms' recent days (``rooms.topic_recent_days``) and the paste-ready scheduler
lines. No new window."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import text_fonts as fonts
from cli_avatars.app import memory_actions as ma
from cli_avatars.app import memory_notes as mn
from cli_avatars.app import topic_rooms as tr

BG, FG, SEL, DIM, OK, BAD = "#0d0d1a", "#aaccff", "#223366", "#9a98b8", "#7dff8a", "#ff8866"


def mount(app, parent) -> dict:
    font, small = fonts.face(9), fonts.face(8)
    out: dict = {}

    def row(label: str, value: str, width: int = 10):
        tk.Label(parent, text=label, bg=BG, fg=FG, font=font, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        line = tk.Frame(parent, bg=BG, pady=3)
        line.pack(fill="x", padx=12)
        entry = tk.Entry(line, bg=SEL, fg=FG, insertbackground=FG, font=font, relief="flat", width=width)
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=width > 8)
        return line, entry

    def flash(button, why: str) -> None:
        button.config(text=why or "Saved", fg=BAD if why else OK)
        parent.after(2400, lambda: button.config(text=button._label, fg=FG))

    def button(line, text, command):
        found = tk.Button(line, text=text, bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                          font=font, relief="flat", padx=8, cursor="hand2", command=command)
        found._label = text
        found.pack(side="left", padx=(6, 0))
        return found

    config = getattr(app, "config", None)
    line, out["root"] = row("Notes folder (memory)", str(mn.root(config)))
    out["save_root"] = button(line, "Save", lambda: flash(out["save_root"], _store_root(app, out["root"].get())))
    out["create"] = button(line, "Create", lambda: flash(out["create"], _create(app, out["root"].get())))
    line, out["at"] = row("Consolidate every night at (HH:MM)", ma.consolidate_at(config), 6)
    out["save_at"] = button(line, "Save", lambda: flash(out["save_at"], _store(app, "memory", "consolidate_at",
                                                                               _clock(out["at"].get()))))
    line, out["days"] = row("Topic rooms: recent for (days)", f"{tr.recent_days(config):g}", 6)
    out["save_days"] = button(line, "Save", lambda: flash(out["save_days"], _store(app, "rooms", "topic_recent_days",
                                                                                   _days(out["days"].get()))))
    tk.Label(parent, text="Nightly run: paste one line once (Windows: Command Prompt; macOS/Linux: crontab -e).",
             bg=BG, fg=DIM, font=small, anchor="w", justify="left", wraplength=320).pack(fill="x", padx=12,
                                                                                       pady=(10, 0))
    lines = ma.scheduler_lines(mn.root(config), ma.consolidate_at(config))
    for key, label in (("windows", "Windows Task Scheduler"), ("cron", "cron")):
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(head, text=label, bg=BG, fg=FG, font=small).pack(side="left")
        text = tk.Text(parent, height=3, wrap="char", bg=SEL, fg=FG, font=small, relief="flat")
        text.insert("1.0", lines[key])
        text.config(state="disabled")
        text.pack(fill="x", padx=12)
        out[key] = text
        button(head, "Copy", lambda t=lines[key]: _copy(parent, t))
    tk.Label(parent, text="The app only writes its inbox. The curator merges it, commits once and pushes to your "
             "private remote; your notes never leave this PC otherwise.", bg=BG, fg=DIM, font=small, anchor="w",
             justify="left", wraplength=320).pack(fill="x", padx=12, pady=(8, 8))
    return out


def _clock(raw: str):
    value = ma.consolidate_at({"memory": {"consolidate_at": raw}})
    return value if value == raw.strip().zfill(5) else None


def _days(raw: str):
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if 0 <= value <= 365 else None


def _store_root(app, raw: str) -> str:
    path = Path(raw.strip()).expanduser()
    if not raw.strip() or not path.is_absolute():
        return "Pick a full folder path."
    return _store(app, "memory", "root", str(path))


def _create(app, raw: str) -> str:
    why = _store_root(app, raw)
    return why or mn.create(mn.root(getattr(app, "config", None)))


def _store(app, section: str, key: str, value) -> str:
    """One key in config.json and the live config; ``""`` when saved."""
    from cli_avatars.app.config_file import save_config_with

    if value is None:
        return "Not a valid value."
    config = dict(getattr(app, "config", None) or {})
    own = config.get(section) if isinstance(config.get(section), dict) else {}
    app.config = {**config, section: {**own, key: value}}

    def update(data: dict) -> dict:
        mine = data.get(section) if isinstance(data.get(section), dict) else {}
        return {**data, section: {**mine, key: value}}

    target = getattr(app, "_config_path", None)
    return "" if target is None or save_config_with(Path(target), update) else "The setting was not stored."


def _copy(widget, text: str) -> None:
    try:
        widget.clipboard_clear()
        widget.clipboard_append(text)
    except tk.TclError:
        return
