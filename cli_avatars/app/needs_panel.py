"""NEEDS-YOU.1 desktop: the "Needs you (N)" tab of the Dungeon's right dock.

``step`` runs from the overlay tick. At most once a second it checks the sources' stamp and reads the list
only when it moved. Rows are kept per item and changed in place; between reads only the age text moves.
An item that enters plays the soft ``arrive`` cue (a new decision already rings ``decide``). The first
read after a start is quiet. A row click opens the task card or the room chat; Clear clears that row.
FOCUS: while a task is in focus only its rows show; new rows of other tasks are held (``focus.gate``), silent,
and the note says how many wait.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk

import focus
import needs_you
from cli_avatars.app import cues
from cli_avatars.app.throttle import StoreThrottle
from events import EventRejected

REFRESH_S = 1.0
_BG = "#141018"
_ROW = "#1d1726"
_HOVER = "#272033"
_EDGE = "#3a3348"
_INK = "#e8e6f4"
_DIM = "#9a98b8"
# kind -> (accent, tag, 8x8 icon)
KINDS = {
    "decision": ("#ffcf4a", "DECISION", ("...aa...", "..aaaa..", ".aa##aa.", "aaa##aaa", "aaa##aaa", ".aaaaaa.",
                                         "..a##a..", "...aa...")),
    "blocked": ("#e0566a", "BLOCKED", ("..aaaa..", ".a....a.", ".a....a.", "aaaaaaaa", "aaa##aaa", "aaa##aaa",
                                       "aaaaaaaa", "........")),
    "reply": ("#7aa8ff", "REPLY", ("aaaaaaaa", "a######a", "a#aa#a#a", "a######a", "aaaaaaaa", "..aa....",
                                   ".a......", "........")),
    "run": ("#6ad08a", "RUN ENDED", ("........", "......aa", ".....aa.", "a...aa..", "aa.aa...", ".aaa....",
                                     "..a.....", "........")),
    "mail": ("#e0b878", "MAILROOM", ("........", "aaaaaaaa", "aa####aa", "a#aa#a#a", "a##aa##a", "a######a",
                                     "aaaaaaaa", "........")),
    "courier": ("#c9a2ff", "NEWS", ("..aaaa..", ".a####a.", "aa#aa#aa", "a######a", "a#aaaa#a", "aa####aa",
                                     ".aaaaaa.", "...aa...")),
}


def step(app, now: float | None = None) -> None:
    gate = getattr(app, "_needs_gate", None)
    if gate is None:
        gate = app._needs_gate = StoreThrottle(REFRESH_S)
    if not gate.due(now):
        return
    gate.mark(now)
    try:
        directory = app._chat_directory()
        mark = (needs_you.stamp(directory), focus.stamp(directory))
        if mark != getattr(app, "_needs_stamp", None):
            items, app._needs_waiting = focus.gate(directory, needs_you.pending(directory))
            app._needs_stamp = mark
            _take(app, items)
    except (EventRejected, OSError):
        return
    except Exception:
        logging.getLogger("cli_avatars.needs_you").exception("needs-you read failed")
        return
    paint(app)


def _take(app, items: list[dict]) -> None:
    seen = getattr(app, "_needs_seen", None)
    app._needs_items = items
    app._needs_seen = {row["key"] for row in items}
    if seen is not None and any(row["key"] not in seen and row["kind"] not in ("decision", "mail") for row in items):
        cues.play(app, "arrive")


def paint(app) -> None:
    """The tab's count and the panel's rows, in place."""
    items = getattr(app, "_needs_items", None) or []
    tab = getattr(getattr(app, "dungeon", None), "_rtab_needs", None)
    if tab is not None:
        text = f"Needs you ({len(items)})" if items else "Needs you"
        if tab.button.cget("text") != text:
            tab.button.config(text=text)
    panel = getattr(app, "_needs_panel", None)
    if panel is not None:
        panel.show(items, time.time(), getattr(app, "_needs_waiting", 0))


def ensure(view) -> None:
    """Build the panel in the dock's Needs tab once."""
    app = view.app
    if getattr(app, "_needs_panel", None) is not None:
        return
    panel = NeedsPanel(view._needs, lambda item: open_item(app, item), lambda item: clear_item(app, item))
    panel.frame.pack(fill="both", expand=True)
    app._needs_panel = panel
    paint(app)


def open_item(app, item: dict) -> None:
    """A card item opens its card on the Tasks tab; a room item opens that room's chat in the dock."""
    view = getattr(app, "dungeon", None)
    if item.get("kind") == "mail" and view is not None:
        view.show_center("mailroom")
        return
    if item.get("card") and view is not None:
        view.show_center("tasks")
        panel = getattr(app, "_tasks_panel", None)
        if panel is not None:
            panel.open_card(item["card"])
        return
    if item.get("room"):
        app._show_chat(topic_id=item["room"])


def clear_item(app, item: dict) -> None:
    try:
        needs_you.clear(app._chat_directory(), item["key"])
    except (EventRejected, OSError):
        return
    app._needs_stamp = app._needs_gate = None
    step(app)


def ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "now"


class NeedsPanel:
    """The list. ``open_item`` and ``clear_item`` take one item dict."""

    def __init__(self, parent, open_item, clear_item):
        self.frame = tk.Frame(parent, bg=_BG)
        self._open, self._clear = open_item, clear_item
        head = tk.Frame(self.frame, bg=_BG)
        head.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(head, text="Waiting on you", bg=_BG, fg="#88aaff", font="DungeonTitle").pack(side="left")
        self.note = tk.Label(head, text="", bg=_BG, fg=_DIM, font="DungeonBubble")
        self.note.pack(side="right")
        self.canvas = tk.Canvas(self.frame, bg=_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=_BG)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.empty = tk.Label(self.body, text="Nothing waits on you.", bg=_BG, fg=_DIM, font="DungeonText")
        self.rows: dict[str, _Row] = {}
        self.order: list[str] = []

    def show(self, items: list[dict], now: float, waiting: int = 0) -> None:
        keys = [item["key"] for item in items]
        for key in set(self.rows) - set(keys):
            self.rows.pop(key).frame.destroy()
        for item in items:
            row = self.rows.get(item["key"])
            if row is None:
                row = self.rows[item["key"]] = _Row(self, item)
            row.set(item, now)
        if keys != self.order:
            for row in self.rows.values():
                row.frame.pack_forget()
            for key in keys:
                self.rows[key].frame.pack(fill="x", padx=8, pady=3)
            self.order = keys
        if keys and self.empty.winfo_manager():
            self.empty.pack_forget()
        elif not keys and not self.empty.winfo_manager():
            self.empty.pack(pady=24)
        note = f"{len(keys)} item{'s' if len(keys) != 1 else ''}" if keys else ""
        if waiting:
            note = f"{note} · {waiting} waiting (focus)" if note else f"{waiting} waiting (focus)"
        if self.note.cget("text") != note:
            self.note.config(text=note)

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


class _Row:
    def __init__(self, panel: NeedsPanel, item: dict):
        self.item = item
        accent = KINDS[item["kind"]][0]
        self.frame = tk.Frame(panel.body, bg=_ROW, highlightthickness=1, highlightbackground=_EDGE, cursor="hand2")
        self.stripe = tk.Frame(self.frame, bg=accent, width=3)
        self.stripe.pack(side="left", fill="y")
        self.icon = tk.Canvas(self.frame, width=16, height=16, bg=_ROW, highlightthickness=0, bd=0)
        self.icon.pack(side="left", anchor="n", padx=(7, 6), pady=8)
        self.clear = tk.Button(self.frame, text="Clear", command=lambda: panel._clear(self.item), bg="#223366",
                               fg="#aaccff", activebackground="#334477", activeforeground="white",
                               font="DungeonBubble", relief="flat", padx=6, pady=1, cursor="hand2")
        self.clear.pack(side="right", anchor="n", padx=6, pady=7)
        text = tk.Frame(self.frame, bg=_ROW)
        text.pack(side="left", fill="x", expand=True, pady=5)
        top = tk.Frame(text, bg=_ROW)
        top.pack(fill="x")
        self.tag = tk.Label(top, text="", bg=_ROW, fg=accent, font="DungeonBubble")
        self.tag.pack(side="left")
        self.age = tk.Label(top, text="", bg=_ROW, fg=_DIM, font="DungeonBubble")
        self.age.pack(side="left", padx=(6, 0))
        self.title = tk.Label(text, text="", bg=_ROW, fg=_INK, font="DungeonText", anchor="w", justify="left")
        self.title.pack(fill="x")
        self.detail = tk.Label(text, text="", bg=_ROW, fg=_DIM, font="DungeonBubble", anchor="w", justify="left",
                               wraplength=220)
        self.detail.pack(fill="x")
        self.detail.bind("<Configure>", lambda e: self.detail.config(wraplength=max(80, e.width - 4)))
        self._kind = ""
        for widget in (self.frame, text, top, self.icon, self.tag, self.age, self.title, self.detail):
            widget.bind("<Button-1>", lambda _e: panel._open(self.item))
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))
            widget.bind("<MouseWheel>", panel._wheel)

    def set(self, item: dict, now: float) -> None:
        self.item = item
        if item["kind"] != self._kind:
            self._kind = item["kind"]
            accent, tag, pixels = KINDS[item["kind"]]
            self.stripe.config(bg=accent)
            self.tag.config(text=tag, fg=accent)
            self.icon.delete("all")
            for y, line in enumerate(pixels):
                for x, cell in enumerate(line):
                    if cell != ".":
                        self.icon.create_rectangle(x * 2, y * 2, x * 2 + 2, y * 2 + 2, width=0,
                                                   fill=accent if cell == "a" else _ROW)
        for label, value in ((self.title, item["title"]), (self.detail, item["detail"]),
                             (self.age, "· " + ago(now - item["ts"]))):
            if label.cget("text") != value:
                label.config(text=value)

    def _hover(self, on: bool) -> None:
        self.frame.config(highlightbackground=KINDS[self._kind][0] if on else _EDGE)
