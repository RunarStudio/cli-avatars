"""DAILY-RECAP desktop: the "Recap" scroll tab in the Dungeon's centre (docs/daily-recap.md).

A parchment scroll hung on the dungeon wall, drawn in code (``recap_art``). Today by default; ←/→ (or the
arrows on the scroll) walk back through the days the log keeps. Rows are agent → task → lines; a task
click opens its card on the Tasks tab. ``step`` runs from the overlay tick: at most once a second, and only
while the tab is shown, it reads the recap again when a board log or the file tally moved. Rows are keyed
and changed in place (text, then position); nothing is cleared, so live updates do not blink.
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import date

import recap
import text_fonts as fonts
from board.store import LocalStore
from cli_avatars.app import cues, recap_art
from cli_avatars.app.tasks_card import EDGE, INK, SOFT, WINE
from cli_avatars.app.tasks_view import ALL
from cli_avatars.app.throttle import StoreThrottle
from events import EventRejected

REFRESH_S = 1.0
SHOWN_LINES = 8
HEAD_H = 74
ROW_H = {"agent": 28, "task": 22, "line": 16, "more": 16, "empty": 40}
HOVER = "#a0283f"
OFF = "#c4ad80"
_LABELS = (("turns", "turn"), ("summaries", "summary"), ("created", "created"), ("moved", "moved"),
           ("asked", "asked"), ("answered", "answered"), ("blocked", "blocked"), ("unblocked", "unblocked"),
           ("files", "file"), ("commits", "commit"))


def counts_text(counts: dict) -> str:
    parts = []
    for key, word in _LABELS:
        n = counts.get(key, 0)
        if n:
            plural = word if n == 1 or word in ("created", "moved", "asked", "answered", "blocked", "unblocked") \
                else ("summaries" if word == "summary" else word + "s")
            parts.append(f"{n} {plural}")
    return " · ".join(parts)


def rows(built: dict) -> list[dict]:
    """Display rows of a recap, top to bottom: ``key``, ``kind``, ``text``, ``side``, ``card``, ``agent``."""
    out = []
    for agent in built["agents"]:
        aid = agent["agent"]
        out.append({"key": f"agent:{aid}", "kind": "agent", "text": agent["name"],
                    "side": counts_text(agent["counts"]), "card": None, "agent": aid})
        for task in agent["tasks"]:
            tkey = f"task:{aid}:{task['card']}"
            out.append({"key": tkey, "kind": "task", "text": task["title"], "side": counts_text(task["counts"]),
                        "card": task["card"], "agent": aid})
            lines = task["lines"]
            tail = [ln for ln in lines if ln.startswith(("files: ", "commits: "))]
            body = [ln for ln in lines if ln not in tail]
            if len(body) > SHOWN_LINES:
                out.append({"key": f"{tkey}:more", "kind": "more", "text": f"… {len(body) - SHOWN_LINES} earlier",
                            "side": "", "card": None, "agent": aid})
                body = body[-SHOWN_LINES:]
            for line in body + tail:
                tag = line.split(":", 1)[0] if line in tail else f"{line[:5]}:{line[6:40]}"
                out.append({"key": f"{tkey}:{tag}", "kind": "line", "text": line, "side": "", "card": None,
                            "agent": aid})
    if not out:
        out.append({"key": "empty", "kind": "empty", "text": "Nothing was logged this day.", "side": "",
                    "card": None, "agent": ""})
    return _unique(out)


def _unique(found: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    for row in found:
        n = seen.get(row["key"], 0)
        seen[row["key"]] = n + 1
        if n:
            row["key"] = f"{row['key']}#{n}"
    return found


def step(app, now: float | None = None) -> None:
    panel = getattr(app, "_recap_panel", None)
    view = getattr(app, "dungeon", None)
    if panel is None or view is None or getattr(view, "_center", "") != "recap":
        return
    gate = getattr(app, "_recap_gate", None)
    if gate is None:
        gate = app._recap_gate = StoreThrottle(REFRESH_S)
    if not gate.due(now):
        return
    gate.mark(now)
    panel.refresh()


def ensure(view) -> "RecapPanel":
    """Build the scroll in the Recap tab once."""
    app = view.app
    panel = getattr(app, "_recap_panel", None)
    if panel is None:
        panel = RecapPanel(view._recap, app._chat_directory, lambda card: open_task(app, card))
        panel.frame.pack(fill="both", expand=True)
        app._recap_panel = panel
    return panel


def opened(view) -> None:
    """The tab was opened: show today's state at once, focus the scroll, play the soft ``scroll`` cue."""
    panel = ensure(view)
    panel.refresh(force=True)
    panel.canvas.focus_set()
    cues.play(view.app, "scroll")


def open_task(app, card: str) -> None:
    """Open the card on the Tasks tab; the board turns to the card's project and topic when it shows another."""
    view = getattr(app, "dungeon", None)
    if view is None:
        return
    view.show_center("tasks")
    panel = getattr(app, "_tasks_panel", None)
    if panel is None:
        return
    found = LocalStore(app._chat_directory()).get(card) if hasattr(panel, "set_filter") else None
    if found is not None and panel._topic() not in (ALL, found["topic"]):
        panel.set_filter(project=found["project"], topic=found["topic"] or ALL)
    panel.open_card(card)


class RecapPanel:
    """The scroll. ``directory()`` gives the data dir; ``open_card(card_id)`` opens a card."""

    def __init__(self, parent, directory, open_card):
        self.frame = tk.Frame(parent, bg="#141018")
        self._directory, self._open = directory, open_card
        self.canvas = tk.Canvas(self.frame, bg="#0c0a0f", highlightthickness=0, bd=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        self.today = date.today()
        self.day = self.today
        self.order: list[str] = []
        self.items: dict[str, int] = {}
        self._extra: dict[str, list[int]] = {}
        self._rows: dict[str, dict] = {}
        self._y: dict[str, int] = {}
        self._mark = None
        self._built: dict | None = None
        self._size = (0, 0)
        self._scroll = 0
        self._images: dict = {}
        self.rebuilds = 0
        self._bg = self.canvas.create_image(0, 0, anchor="nw", tags=("bg",))
        self._title = self.canvas.create_text(0, 0, text="Daily recap", fill=INK, font=fonts.face(15, "bold"),
                                              tags=("head",))
        self._day = self.canvas.create_text(0, 0, text="", fill=WINE, font="DungeonTitle", tags=("head",))
        self._prev = self.canvas.create_text(0, 0, text="◄", fill=WINE, font=fonts.face(14, "bold"),
                                             tags=("head", "nav"))
        self._next = self.canvas.create_text(0, 0, text="►", fill=WINE, font=fonts.face(14, "bold"),
                                             tags=("head", "nav"))
        self._totals = self.canvas.create_text(0, 0, text="", fill=SOFT, font="DungeonBubble", tags=("head",))
        self._rule = self.canvas.create_line(0, 0, 0, 0, fill=EDGE, width=2, dash=(6, 2, 2, 2), tags=("head",))
        self._flourish = [self.canvas.create_line(0, 0, 0, 0, fill=EDGE, width=2, tags=("head",)) for _ in range(2)]
        self._diamonds = [self.canvas.create_polygon(0, 0, 0, 0, 0, 0, fill=WINE, outline=EDGE, tags=("head",))
                          for _ in range(4)]
        self.canvas.tag_bind(self._prev, "<Button-1>", lambda _e: self.go(-1))
        self.canvas.tag_bind(self._next, "<Button-1>", lambda _e: self.go(1))
        for item in (self._prev, self._next):
            self.canvas.tag_bind(item, "<Enter>", lambda _e, i=item: self._hover(i, True))
            self.canvas.tag_bind(item, "<Leave>", lambda _e, i=item: self._hover(i, False))
        self.canvas.bind("<Left>", lambda _e: self.go(-1))
        self.canvas.bind("<Right>", lambda _e: self.go(1))
        self.canvas.bind("<Button-1>", lambda _e: self.canvas.focus_set(), add="+")
        self.canvas.bind("<MouseWheel>", lambda e: self.scroll(-1 if e.delta > 0 else 1))
        self.canvas.bind("<Button-4>", lambda _e: self.scroll(-1))
        self.canvas.bind("<Button-5>", lambda _e: self.scroll(1))
        self.canvas.bind("<Configure>", lambda _e: self._resize())

    def title_text(self) -> str:
        return self.canvas.itemcget(self._day, "text")

    def texts(self) -> list[str]:
        return [self._rows[k]["text"] for k in self.order]

    def open_task(self, card: str) -> None:
        self._open(card)

    def go(self, delta: int) -> None:
        today = date.today()
        day = recap.step(self.day, delta, today)
        if day != self.day:
            self.day, self._scroll = day, 0
            self.refresh(force=True)

    def scroll(self, direction: int) -> None:
        self._scroll = max(0, self._scroll + direction * 48)
        self._place()

    def refresh(self, force: bool = False) -> None:
        today = date.today()
        if today != self.today:
            if self.day == self.today:
                self.day = today
            self.today, force = today, True
        try:
            directory = self._directory()
            mark = (recap.stamp(directory), self.day)
            if not force and mark == self._mark:
                return
            built = recap.build(directory, self.day, today=today)
        except (EventRejected, OSError):
            return
        except Exception:
            logging.getLogger("cli_avatars.recap").exception("recap read failed")
            return
        self._mark = mark
        self.show(built)

    def show(self, built: dict) -> None:
        """Change rows in place: new keys are drawn, gone keys removed, kept keys get new text and spot."""
        self._built = built
        new = rows(built)
        if not self.items:
            self.rebuilds += 1
        keys = [row["key"] for row in new]
        for key in set(self.items) - set(keys):
            self.canvas.delete(self.items.pop(key), *self._extra.pop(key, []))
            self._rows.pop(key, None)
        for row in new:
            if row["key"] in self.items:
                self._update(row)
            else:
                self._draw(row)
        self.order = keys
        self._head(built)
        self._place()

    def _head(self, built: dict) -> None:
        label = built["label"]
        when = date.fromisoformat(built["day"])
        text = label if label not in ("Today", "Yesterday") else f"{label} · {when:%a} {when.day} {when:%b}"
        self.canvas.itemconfigure(self._day, text=text)
        agents = len(built["agents"])
        tasks = built["tasks"]
        total = counts_text(built["totals"])
        summary = f"{agents} agent{'s' * (agents != 1)} · {tasks} task{'s' * (tasks != 1)}"
        self.canvas.itemconfigure(self._totals, text=summary + (f" · {total}" if total else ""))
        kept = recap.days(self.today)
        self.canvas.itemconfigure(self._prev, fill=OFF if self.day == kept[-1] else WINE)
        self.canvas.itemconfigure(self._next, fill=OFF if self.day == kept[0] else WINE)

    def _draw(self, row: dict) -> None:
        kind, key, c = row["kind"], row["key"], self.canvas
        font = {"agent": "DungeonTitle", "task": "DungeonText", "line": "DungeonBubble", "more": "DungeonBubble",
                "empty": "DungeonText"}[kind]
        fill = {"agent": INK, "task": WINE if row["card"] else SOFT, "line": SOFT, "more": EDGE, "empty": SOFT}[kind]
        main = c.create_text(0, 0, text=row["text"], anchor="w", fill=fill, font=font, tags=("row",))
        extra = []
        if kind in ("agent", "task"):
            extra.append(c.create_text(0, 0, text=row["side"], anchor="e", fill=SOFT, font="DungeonBubble",
                                       tags=("row",)))
            extra.append(c.create_image(0, 0, image=self._icon(row), anchor="w", tags=("row",)))
        if kind == "agent":
            extra.append(c.create_line(0, 0, 0, 0, fill="#b89a64", tags=("row",)))
        if kind == "task" and row["card"]:
            card = row["card"]
            c.tag_bind(main, "<Button-1>", lambda _e: self.open_task(card))
            c.tag_bind(main, "<Enter>", lambda _e, i=main: self._hover(i, True))
            c.tag_bind(main, "<Leave>", lambda _e, i=main: self._hover(i, False))
        self.items[key], self._extra[key], self._rows[key] = main, extra, row

    def _update(self, row: dict) -> None:
        key, old = row["key"], self._rows[row["key"]]
        if old["text"] != row["text"]:
            self.canvas.itemconfigure(self.items[key], text=row["text"])
        if old["side"] != row["side"]:
            self.canvas.itemconfigure(self._extra[key][0], text=row["side"])
        self._rows[key] = row

    def _icon(self, row: dict):
        from PIL import ImageTk

        name = ("seal", recap_art.seal_color(row["agent"])) if row["kind"] == "agent" else \
            ("gem", "#7a1f3d" if row["card"] else "#8a6a3a")
        if name not in self._images:
            art = recap_art.seal(name[1]) if name[0] == "seal" else recap_art.gem(name[1])
            self._images[name] = ImageTk.PhotoImage(art, master=self.canvas)
        return self._images[name]

    def _place(self) -> None:
        """Lay rows out under the head, clip them to the parchment, keep the scroll inside the content."""
        box = recap_art.layout(*self._canvas_size())["text"]
        x0, y0, x1, y1 = box
        mid = (x0 + x1) // 2
        c = self.canvas
        c.coords(self._title, mid, y0 + 12)
        c.coords(self._day, mid, y0 + 36)
        c.coords(self._prev, mid - 150, y0 + 36)
        c.coords(self._next, mid + 150, y0 + 36)
        c.coords(self._totals, mid, y0 + 54)
        c.coords(self._rule, x0, y0 + HEAD_H - 8, x1, y0 + HEAD_H - 8)
        ty = y0 + 13
        for i, sign in enumerate((-1, 1)):
            near, far = mid + sign * 96, mid + sign * 190
            c.coords(self._flourish[i], near, ty, far, ty)
            for j, x in enumerate((near + sign * 2, far)):
                c.coords(self._diamonds[i * 2 + j], x, ty - 4, x + 4, ty, x, ty + 4, x - 4, ty)
        top, bottom = y0 + HEAD_H, y1
        height = sum(ROW_H[self._rows[k]["kind"]] for k in self.order)
        self._scroll = max(0, min(self._scroll, height - (bottom - top)))
        y = top - self._scroll
        chars = max(10, (x1 - x0 - 60) // 7)
        for key in self.order:
            row = self._rows[key]
            h = ROW_H[row["kind"]]
            inside = top <= y and y + h <= bottom + 2
            state = "normal" if inside else "hidden"
            indent = {"agent": 20, "task": 36, "line": 52, "more": 52, "empty": 0}[row["kind"]]
            cy = y + h // 2
            main = self.items[key]
            if row["kind"] == "empty":
                c.coords(main, mid, top + 30)
                c.itemconfigure(main, anchor="center", state=state)
            else:
                c.coords(main, x0 + indent, cy)
                c.itemconfigure(main, state=state)
                text = row["text"] if len(row["text"]) <= chars - indent // 7 else \
                    row["text"][:chars - indent // 7 - 1] + "…"
                if c.itemcget(main, "text") != text and row["kind"] == "line":
                    c.itemconfigure(main, text=text)
            extra = self._extra.get(key, [])
            if row["kind"] in ("agent", "task"):
                c.coords(extra[0], x1, cy)
                c.coords(extra[1], x0 + indent - (18 if row["kind"] == "agent" else 14), cy)
                for item in extra[:2]:
                    c.itemconfigure(item, state=state)
            if row["kind"] == "agent":
                c.coords(extra[2], x0 + 4, y + h - 3, x1, y + h - 3)
                c.itemconfigure(extra[2], state=state)
            y += h

    def _canvas_size(self) -> tuple[int, int]:
        try:
            return max(200, int(self.canvas.winfo_width())), max(200, int(self.canvas.winfo_height()))
        except tk.TclError:
            return 200, 200

    def _resize(self) -> None:
        size = self._canvas_size()
        if size == self._size:
            return
        self._size = size
        from PIL import ImageTk

        self._images["bg"] = ImageTk.PhotoImage(recap_art.scroll(*size), master=self.canvas)
        self.canvas.itemconfigure(self._bg, image=self._images["bg"])
        self._place()

    def _hover(self, item: int, on: bool) -> None:
        if item in (self._prev, self._next):
            kept = recap.days(self.today)
            if self.day == (kept[-1] if item == self._prev else kept[0]):
                return
        self.canvas.itemconfigure(item, fill=HOVER if on else WINE)
        self.canvas.configure(cursor="hand2" if on else "")

