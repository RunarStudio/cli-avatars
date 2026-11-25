"""MAILROOM desktop: the "Mailroom" tab in the Dungeon's centre (docs/mailroom.md).

A room drawn in code (``mail_art``): a pigeonhole shelf whose cubbies fill as letters wait, a mail sack, and a
sorting board where each letter hangs as a slip with the sorter's topic, task chat and draft decision.
Approve (Enter or A) files it, Bounce (B or Delete) sends it to Unsorted or drops an unsorted one, T picks the
next ranked topic, a click on the topic chip lists them all; Up and Down select. ``step`` runs from the overlay
tick: at most once a second it takes in new lines (``mailroom.ingest``) and redraws only when the store or
focus moved. Slips are keyed and changed in place. New letters play the ``letter`` cue once per batch, silent
while a task is in focus; filing plays ``filed``.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk

import focus
import mailroom
from cli_avatars.app import cues, mail_art
from cli_avatars.app.tasks_card import EDGE, GOLD, INK, PARCH, WINE
from cli_avatars.app.throttle import StoreThrottle
from events import EventRejected

REFRESH_S = 1.0
TOAST_MS = 2200
SLIP_H, SMALL_H, GAP, HEAD = 112, 46, 10, 46
TEXT_CHARS = 140
SOURCE = {"capture": "✎ THOUGHT", "message": "✉ MESSAGE", "hook": "⚑ HOOK"}
GREEN, RED, CHIP = "#2f6a3a", "#8a2a2a", "#3a2a1c"


def step(app, now: float | None = None) -> None:
    gate = getattr(app, "_mail_gate", None)
    if gate is None:
        gate = app._mail_gate = StoreThrottle(REFRESH_S)
    if not gate.due(now):
        return
    gate.mark(now)
    try:
        directory = app._chat_directory()
        mailroom.ingest(directory)
        mark = (mailroom.stamp(directory), focus.stamp(directory))
        if mark == getattr(app, "_mail_stamp", None):
            return
        app._mail_stamp = mark
        _take(app, mailroom.public(directory), focus.current(directory) is not None)
    except (EventRejected, OSError):
        return
    except Exception:
        logging.getLogger("cli_avatars.mailroom").exception("mailroom read failed")


def _take(app, state: dict, focused: bool) -> None:
    seen = getattr(app, "_mail_seen", None)
    ids = {i["id"] for i in state["items"]}
    if seen is not None and ids - seen and not focused:
        cues.play(app, "letter")
    app._mail_seen = ids
    app._mail_state = state
    paint(app)


def paint(app) -> None:
    state = getattr(app, "_mail_state", None) or {"items": [], "unsorted": [], "count": 0, "held": 0}
    tab = getattr(getattr(app, "dungeon", None), "_tab_mail", None)
    if tab is not None:
        text = f"Mailroom ({state['count']})" if state["count"] else "Mailroom"
        if tab.button.cget("text") != text:
            tab.button.config(text=text)
    panel = getattr(app, "_mail_panel", None)
    if panel is not None:
        panel.show(state, time.time())


def ensure(view) -> "MailPanel":
    app = view.app
    panel = getattr(app, "_mail_panel", None)
    if panel is None:
        panel = app._mail_panel = MailPanel(view._mail, app)
        panel.frame.pack(fill="both", expand=True)
        paint(app)
    return panel


def opened(view) -> None:
    panel = ensure(view)
    view.app._mail_stamp = None
    step(view.app)
    panel.canvas.focus_set()


def ago(seconds: float) -> str:
    from cli_avatars.app.needs_panel import ago as needs_ago

    return needs_ago(seconds)


class MailPanel:
    """The room and its slips. Actions go through ``mailroom`` on the app's data dir."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent, bg="#141018")
        self.canvas = c = tk.Canvas(self.frame, bg="#0c0a0f", highlightthickness=0, bd=0, takefocus=1)
        c.pack(fill="both", expand=True)
        self.slips: dict[str, dict] = {}
        self.order: list[str] = []
        self.selected = ""
        self.ranked: dict[str, list[str]] = {}
        self.state: dict = {"items": [], "unsorted": [], "count": 0, "held": 0}
        self._images: dict = {}
        self._size = (0, 0)
        self._scroll = 0
        self._toast_job = None
        self._bg = c.create_image(0, 0, anchor="nw")
        self._letters = c.create_image(0, 0, anchor="nw")
        self._sack = c.create_image(0, 0, anchor="nw")
        self._plaque = c.create_text(0, 0, text="MAILROOM", fill="#2a1a08", font="DungeonTitle")
        self._count = c.create_text(0, 0, text="", fill=GOLD, font=("Courier", 22, "bold"))
        self._count_note = c.create_text(0, 0, text="", fill=PARCH, font="DungeonBubble")
        self._title = c.create_text(0, 0, text="Letters to sort", anchor="w", fill=GOLD, font="DungeonTitle")
        self._held = c.create_text(0, 0, text="", anchor="e", fill="#c8b8ff", font="DungeonBubble")
        self._keys = c.create_text(0, 0, text="Enter/A approve · B bounce · T topic · ↑↓ select", anchor="e",
                                   fill=PARCH, font="DungeonBubble")
        self._empty = c.create_text(0, 0, text="No letters. New thoughts and messages land here.", fill=PARCH,
                                    font="DungeonText")
        self._unsorted = c.create_text(0, 0, text="", anchor="w", fill=PARCH, font="DungeonTitle")
        self._toast = c.create_text(0, 0, text="", fill=GOLD, font="DungeonTitle", state="hidden")
        for key, action in (("<Return>", self.approve), ("<KP_Enter>", self.approve), ("a", self.approve),
                            ("b", self.bounce), ("<Delete>", self.bounce), ("t", self.next_topic),
                            ("<Down>", lambda: self.move(1)), ("<Up>", lambda: self.move(-1))):
            c.bind(key, lambda _e, f=action: (f(), "break")[1])
        c.bind("<Button-1>", lambda _e: c.focus_set(), add="+")
        c.bind("<MouseWheel>", lambda e: self.scroll(-1 if e.delta > 0 else 1))
        c.bind("<Button-4>", lambda _e: self.scroll(-1))
        c.bind("<Button-5>", lambda _e: self.scroll(1))
        c.bind("<Configure>", lambda _e: self._resize())

    # --- state -----------------------------------------------------------------------------------------
    def show(self, state: dict, now: float) -> None:
        self.state = state
        rows = [*state["items"], *state["unsorted"]]
        keep = {r["id"] for r in rows}
        for gone in set(self.slips) - keep:
            self.canvas.delete(*self.slips.pop(gone)["ids"])
            self.ranked.pop(gone, None)
        for row in rows:
            if row["id"] not in self.slips:
                self._draw(row)
            self._update(row, now)
        self.order = [r["id"] for r in rows]
        if self.selected not in keep:
            self.selected = self.order[0] if self.order else ""
        n, held, unsorted = state["count"], state["held"], len(state["unsorted"])
        self.canvas.itemconfigure(self._count, text=str(n) if n else "")
        self.canvas.itemconfigure(self._count_note, text=f"letter{'s' if n != 1 else ''} waiting" if n else "")
        self.canvas.itemconfigure(self._held, text=f"{held} held (focus)" if held else "")
        self.canvas.itemconfigure(self._unsorted, text=f"Unsorted · {unsorted}" if unsorted else "")
        self.canvas.itemconfigure(self._empty, state="normal" if not rows else "hidden")
        self._art(n)
        self._place()

    def ids(self) -> list[str]:
        return list(self.order)

    def topic_of(self, item_id: str) -> str:
        return self.slips[item_id]["row"]["topic"]

    def text_of(self, item_id: str, part: str) -> str:
        found = self.slips[item_id][part]
        return self.canvas.itemcget(found[1] if isinstance(found, tuple) else found, "text")

    # --- actions ---------------------------------------------------------------------------------------
    def approve(self, item_id: str | None = None) -> None:
        item_id = item_id or self.selected
        if not item_id:
            return
        try:
            filed = mailroom.approve(self.app._chat_directory(), item_id)
        except (EventRejected, OSError):
            self.toast("The board refused that letter.")
            return
        if filed is None:
            return
        cues.play(self.app, "filed")
        tasks = getattr(self.app, "_tasks_panel", None)
        if tasks is not None:
            tasks.refresh(force=True)
            tasks.flash(filed["card"]["id"])
        where = self.slips.get(item_id, {}).get("row", {}).get("topic_title") or filed["card"]["topic"]
        self.toast(f"✓ Filed in {where}" + (" · chat ready" if filed["room"] else ""))
        self._reload()

    def bounce(self, item_id: str | None = None) -> None:
        item_id = item_id or self.selected
        if item_id and mailroom.bounce(self.app._chat_directory(), item_id):
            self._reload()

    def retopic(self, item_id: str, topic: str) -> None:
        if mailroom.retopic(self.app._chat_directory(), item_id, topic):
            self._reload()

    def next_topic(self, item_id: str | None = None) -> None:
        """The next topic the ranker gives for the letter's text."""
        item_id = item_id or self.selected
        slip = self.slips.get(item_id)
        if slip is None:
            return
        ranked = self.ranked.get(item_id)
        if ranked is None:
            from registry import capture

            row = slip["row"]
            ranked = self.ranked[item_id] = capture.build_index(self.app._chat_directory()).rank(row["text"],
                                                                                                    row["topic"])
        if ranked:
            at = ranked.index(slip["row"]["topic"]) if slip["row"]["topic"] in ranked else -1
            self.retopic(item_id, ranked[(at + 1) % len(ranked)])

    def move(self, delta: int) -> None:
        if self.order:
            at = self.order.index(self.selected) if self.selected in self.order else 0
            self.selected = self.order[max(0, min(len(self.order) - 1, at + delta))]
            self._place()

    def scroll(self, direction: int) -> None:
        self._scroll = max(0, self._scroll + direction * 48)
        self._place()

    def toast(self, text: str) -> None:
        self.canvas.itemconfigure(self._toast, text=text, state="normal")
        self.canvas.tag_raise(self._toast)
        if self._toast_job is not None:
            self.canvas.after_cancel(self._toast_job)
        self._toast_job = self.canvas.after(TOAST_MS, self._hide_toast)

    def _hide_toast(self) -> None:
        self._toast_job = None
        self.canvas.itemconfigure(self._toast, state="hidden")

    def _reload(self) -> None:
        self.app._mail_stamp = self.app._mail_gate = None
        step(self.app)

    def _menu(self, item_id: str, event) -> None:
        menu = tk.Menu(self.canvas, tearoff=0, bg="#1a1218", fg=PARCH, activebackground=GOLD,
                       activeforeground=INK)
        for topic in mailroom.topics(self.app._chat_directory()):
            menu.add_command(label=topic["title"], command=lambda t=topic["id"]: self.retopic(item_id, t))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # --- drawing ---------------------------------------------------------------------------------------
    def _draw(self, row: dict) -> None:
        c, item_id = self.canvas, row["id"]
        slip = {"row": row, "kind": "", "img": c.create_image(0, 0, anchor="nw")}
        slip["ring"] = c.create_rectangle(0, 0, 0, 0, outline=GOLD, width=2, state="hidden")
        slip["tag"] = c.create_text(0, 0, text="", anchor="nw", fill=WINE, font="DungeonBubble")
        slip["text"] = c.create_text(0, 0, text="", anchor="nw", fill=INK, font="DungeonText")
        slip["draft"] = c.create_text(0, 0, text="", anchor="nw", fill=WINE, font="DungeonBubble")
        slip["chip"] = c.create_rectangle(0, 0, 0, 0, fill=CHIP, outline=EDGE)
        slip["topic"] = c.create_text(0, 0, text="", anchor="w", fill=GOLD, font="DungeonBubble")
        buttons = []
        for name, label, color in (("approve", "✓ Approve", GREEN), ("bounce", "↩ Bounce", RED)):
            box = c.create_rectangle(0, 0, 0, 0, fill=color, outline="#1a1010")
            text = c.create_text(0, 0, text=label, fill=PARCH, font="DungeonBubble")
            slip[name] = (box, text)
            buttons += [box, text]
            for part in (box, text):
                c.tag_bind(part, "<Button-1>", lambda _e, n=name: getattr(self, n)(item_id))
                c.tag_bind(part, "<Enter>", lambda _e, b=box: c.itemconfigure(b, outline=GOLD))
                c.tag_bind(part, "<Leave>", lambda _e, b=box: c.itemconfigure(b, outline="#1a1010"))
        for part in (slip["chip"], slip["topic"]):
            c.tag_bind(part, "<Button-1>", lambda e: self._menu(item_id, e))
        for part in (slip["img"], slip["text"], slip["tag"], slip["draft"]):
            c.tag_bind(part, "<Button-1>", lambda _e: self._select(item_id))
        slip["ids"] = [slip["img"], slip["ring"], slip["tag"], slip["text"], slip["draft"], slip["chip"],
                       slip["topic"], *buttons]
        self.slips[item_id] = slip

    def _select(self, item_id: str) -> None:
        self.selected = item_id
        self._place()

    def _update(self, row: dict, now: float) -> None:
        slip, c = self.slips[row["id"]], self.canvas
        if row.get("topic") != slip["row"].get("topic"):
            self.ranked.pop(row["id"], None)
        slip["row"] = row
        where = f" · {row['room']}" if row.get("room") else ""
        sender = "" if row["from"] == "user" else f" · {row['from'].split(':', 1)[0]}"
        text = row["text"] if len(row["text"]) <= TEXT_CHARS else row["text"][:TEXT_CHARS - 1] + "…"
        draft = f"Decide: {row['draft']}" if row.get("draft") else ""
        chat = " · + task chat" if row.get("chat") else ""
        topic = f"→ {row.get('topic_title') or 'no topic'}  ▾"
        tag = f"{SOURCE.get(row['source'], row['source'])}{where}{sender} · {ago(now - row['ts'])}{chat}"
        values = ((slip["tag"], tag),
                  (slip["text"], text), (slip["draft"], draft), (slip["topic"], topic))
        for part, value in values:
            if c.itemcget(part, "text") != value:
                c.itemconfigure(part, text=value)
        c.itemconfigure(slip["bounce"][1], text="✕ Drop" if row["state"] == "unsorted" else "↩ Bounce")

    def _resize(self) -> None:
        size = (max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        if size == self._size:
            return
        self._size = size
        self._images["bg"] = _photo(self.canvas, mail_art.room(*size))
        self.canvas.itemconfigure(self._bg, image=self._images["bg"])
        self._art(self.state["count"], force=True)
        self._place()

    def _art(self, count: int, force: bool = False) -> None:
        key = min(count, mail_art.COLS * mail_art.ROWS * mail_art.PER_CUBBY)
        if force or self._images.get("n") != key:
            self._images["n"] = key
            self._images["letters"] = _photo(self.canvas, mail_art.letters(key))
            self._images["sack"] = _photo(self.canvas, mail_art.sack(min(count, 3)))
            self.canvas.itemconfigure(self._letters, image=self._images["letters"])
            self.canvas.itemconfigure(self._sack, image=self._images["sack"])

    def _place(self) -> None:
        if self._size == (0, 0):
            return
        c, box = self.canvas, mail_art.layout(*self._size)
        sx0, sy0, sx1, sy1 = box["shelf"]
        c.coords(self._letters, sx0, sy0)
        c.coords(self._sack, *box["sack"][:2])
        p = box["plaque"]
        c.coords(self._plaque, (p[0] + p[2]) / 2, (p[1] + p[3]) / 2)
        c.coords(self._count, (sx0 + sx1) / 2, sy1 + 22)
        c.coords(self._count_note, (sx0 + sx1) / 2, sy1 + 44)
        bx0, by0, bx1, by1 = box["board"]
        left, right = bx0 + 18, bx1 - 18
        c.coords(self._title, left, by0 + 20)
        c.coords(self._keys, right, by0 + 20)
        c.coords(self._held, right, by0 + 36)
        c.coords(self._empty, (bx0 + bx1) / 2, (by0 + by1) / 2)
        c.coords(self._toast, (bx0 + bx1) / 2, by1 - 24)
        y = by0 + HEAD - self._scroll
        first = True
        for item_id in self.order:
            slip = self.slips[item_id]
            small = slip["row"]["state"] == "unsorted"
            if small and first:
                c.coords(self._unsorted, left, y + 12)
                y += 28
                first = False
            height = SMALL_H if small else SLIP_H
            self._slip(slip, left, y, right, height, small, item_id == self.selected)
            y += height + GAP
        if first:
            c.coords(self._unsorted, -100, -100)
        c.tag_raise(self._toast)

    def _slip(self, slip: dict, x0: int, y0: int, x1: int, height: int, small: bool, selected: bool) -> None:
        c, w = self.canvas, x1 - x0
        kind = (w, height, "unsorted" if small else "new")
        if slip["kind"] != kind:
            slip["kind"] = kind
            slip["photo"] = _photo(c, mail_art.slip(*kind))
            c.itemconfigure(slip["img"], image=slip["photo"])
        c.coords(slip["img"], x0, y0)
        c.coords(slip["ring"], x0 - 3, y0 - 3, x0 + w + 3, y0 + height + 3)
        c.itemconfigure(slip["ring"], state="normal" if selected else "hidden")
        pad = 14
        bw, bh, by = 92, 22, y0 + height - 32 if not small else y0 + 12
        cx = x1 - pad - bw
        for name in ("bounce", "approve"):
            box, text = slip[name]
            c.coords(box, cx, by, cx + bw, by + bh)
            c.coords(text, cx + bw / 2, by + bh / 2)
            cx -= bw + 8
        chip_w = min(260, max(120, len(c.itemcget(slip["topic"], "text")) * 7 + 16))
        chip_x = x1 - pad - chip_w if not small else cx - chip_w + bw
        chip_y = y0 + 8 if not small else y0 + 12
        c.coords(slip["chip"], chip_x, chip_y, chip_x + chip_w, chip_y + 20)
        c.coords(slip["topic"], chip_x + 8, chip_y + 10)
        c.coords(slip["tag"], x0 + pad, y0 + 9)
        c.coords(slip["text"], x0 + pad, y0 + (32 if not small else 22))
        if small:
            room = max(8, (chip_x - x0 - 2 * pad) // 7)
            text = slip["row"]["text"]
            c.itemconfigure(slip["text"], width=0, text=text if len(text) <= room else text[:room - 1] + "…")
        else:
            c.itemconfigure(slip["text"], width=w - 2 * pad)
        c.coords(slip["draft"], x0 + pad, y0 + height - 26)
        c.itemconfigure(slip["draft"], state="hidden" if small else "normal", width=w - 2 * pad - 2 * bw - 20)


def _photo(master, image):
    from PIL import ImageTk

    return ImageTk.PhotoImage(image, master=master)
