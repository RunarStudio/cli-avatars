"""GROK-CHAT: the Grok topics strip in the chat dock, shown while the Grok chip is lit. No new window.

One row per Grok conversation (``grok_topics.rows``): a pixel diamond lit by its state (answering pulses, live glows,
idle dims, new is hollow), the title, a room/task/topic tag, the time and the last line. A click switches the chat
and the composer to that conversation; **+ New Grok topic** makes one bound to the room shown; **Read aloud** speaks
the newest Grok reply and **Auto-read** speaks each new one (``grok_voice``). Nothing here starts a CLI.
"""

from __future__ import annotations

import time
import tkinter as tk
from types import SimpleNamespace

import text_fonts as fonts
from cli_avatars.app import grok_cues, grok_topics, grok_voice, room_log
from cli_avatars.app.chat_clis import COLORS
from cli_avatars.app.cli_chips import EDGE, FACE, FONT, INK, OFF_INK, PLATE, PX
from cli_avatars.app.toolbar_widgets import wrap_tabs
from events import EventRejected

GROK = COLORS["grok"]
BRIGHT, DIM = "#cfe2ff", "#3a4a66"
SHOWN = 4
DIAMOND = ("00100", "01110", "11111", "01110", "00100")
HOLLOW = ("00100", "01010", "10001", "01010", "00100")
TAGS = {"room": "room", "task": "task", "topic": "topic"}


class GrokList:
    """Built once per mount by ``RoomPane``; ``refresh`` rereads the rows."""

    def __init__(self, pane, parent) -> None:
        self.pane = pane
        self.auto_read = False
        self.frame = tk.Frame(parent, bg=EDGE, padx=1, pady=1)
        head = tk.Frame(self.frame, bg=PLATE)
        head.pack(fill="x")
        name = tk.Label(head, text="◆ Grok topics", bg=PLATE, fg=GROK, font=FONT)
        self.auto_btn = self._button(head, "Auto-read: off", self.toggle_auto)
        self.read_btn = self._button(head, "Read aloud", self.read_aloud)
        wrap_tabs(head, [name, self._button(head, "+ New Grok topic", self.new_topic), self.read_btn, self.auto_btn])
        self.body = tk.Frame(self.frame, bg=PLATE)
        self.body.pack(fill="x")
        self.rows: list[dict] = []

    def refresh(self) -> None:
        directory = self.pane.window.directory()
        busy = getattr(self.pane.tools, "running", None)
        try:
            self.rows = grok_topics.rows(directory, running=busy and (lambda room: busy(room, "grok")))
        except OSError:
            self.rows = []
        self.paint()

    def paint(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        if not self.rows:
            tk.Label(self.body, text="No Grok conversations yet. Send to Grok here, or + New Grok topic.",
                     bg=PLATE, fg=OFF_INK, font=fonts.face(8), anchor="w").pack(fill="x", padx=6, pady=3)
        current = [r for r in self.rows if r["room"] == self.pane.room_id]
        for row in (current + [r for r in self.rows if r["room"] != self.pane.room_id])[:SHOWN]:
            self._row(row, row["room"] == self.pane.room_id)
        more = len(self.rows) - SHOWN
        if more > 0:
            tk.Label(self.body, text=f"+{more} more (phone: Grok topics)", bg=PLATE, fg=OFF_INK,
                     font=fonts.face(8), anchor="w").pack(fill="x", padx=6)
        self.read_btn.config(state="normal" if grok_voice.available() else "disabled")
        self.auto_btn.config(text=f"Auto-read: {'on' if self.auto_read else 'off'}")

    def pick(self, room: str) -> None:
        """Daniel's click: show this conversation with the Grok chip lit."""
        self.pane.window._select(room)
        self.pane.sync(room)
        self.pane.pick_target("grok")
        self.paint()

    def new_topic(self) -> None:
        bound = self.pane.room_id
        try:
            room = grok_topics.new_topic(self.pane.window.directory(), bound)
        except (EventRejected, OSError) as exc:
            self.pane._status(f"No new Grok topic: {exc}")
            return
        self.refresh()
        self.pick(room)
        self.pane._status("New Grok topic: its own session, in this room's folder. Type and press Enter.")

    def read_aloud(self) -> None:
        text = grok_voice.last_reply(room_log.history(self.pane.window.directory(), self.pane.room_id, "grok"))
        if not grok_voice.available():
            self.pane._status(grok_voice.UNAVAILABLE)
        elif not grok_voice.speak(text):
            self.pane._status("No Grok reply here to read yet.")

    def toggle_auto(self) -> None:
        self.auto_read = not self.auto_read
        if self.auto_read and not grok_voice.available():
            self.pane._status(grok_voice.UNAVAILABLE)
        self.paint()

    def show(self, on: bool, before) -> None:
        if on:
            self.frame.pack(fill="x", padx=8, pady=(2, 0), before=before)
            self.refresh()
        else:
            self.frame.pack_forget()

    def started(self, cli: str) -> None:
        if cli == "grok":
            grok_cues.cue(SimpleNamespace(config=self.pane.window._config()), "grok-send")

    def done(self, cli: str, room: str, texts: list[str], outcome: str) -> None:
        """A Grok turn ended: the reply cue, and on Auto-read the reply spoken when it is the room shown."""
        if cli != "grok":
            return
        if outcome == "ok":
            grok_cues.cue(SimpleNamespace(config=self.pane.window._config()), "grok-reply")
            if self.auto_read and room == self.pane.room_id:
                grok_voice.speak("\n".join(texts))
        self.refresh()

    def _row(self, row: dict, lit: bool) -> None:
        face = FACE if lit else PLATE
        tile = tk.Frame(self.body, bg=GROK if lit else PLATE, padx=1, pady=1, cursor="hand2")
        tile.pack(fill="x", padx=4, pady=1)
        inner = tk.Frame(tile, bg=face)
        inner.pack(fill="x")
        gem = tk.Canvas(inner, width=5 * PX + 2, height=5 * PX + 2, bg=face, highlightthickness=0)
        gem.pack(side="left", padx=(5, 4), pady=3)
        _gem(gem, row["state"])
        text = tk.Frame(inner, bg=face)
        text.pack(side="left", fill="x", expand=True)
        top = tk.Frame(text, bg=face)
        top.pack(fill="x")
        title = tk.Label(top, text=row["title"][:34], bg=face, fg=fonts.OFF_WHITE if lit else INK, font=FONT,
                         anchor="w")
        title.pack(side="left")
        stamp = time.strftime("%H:%M", time.localtime(row["at"])) if row["at"] else ""
        meta = tk.Label(text, text=f"{TAGS.get(row['kind'], '')} · {row['state']} · {stamp}", bg=face, fg=OFF_INK,
                        font=fonts.face(7))
        _fit(top, title, meta)
        if row["last"]:
            tk.Label(text, text=row["last"][:60], bg=face, fg=GROK if lit else "#8a96b0", font=fonts.face(8),
                     anchor="w").pack(fill="x")
        for widget in (tile, inner, gem, text, top, title, *text.winfo_children()):
            widget.bind("<Button-1>", lambda _e, room=row["room"]: self.pick(room))

    def _button(self, parent, text: str, command) -> tk.Button:
        btn = tk.Button(parent, text=text, command=command, font=fonts.face(8), bg="#1d2a44", fg=INK,
                        activebackground=GROK, activeforeground=PLATE, disabledforeground=OFF_INK, relief="flat",
                        padx=5, pady=0)
        btn.pack(side="right", padx=1, pady=2)
        return btn


def _fit(top: tk.Frame, title: tk.Label, meta: tk.Label) -> None:
    """The room/state/time tag beside the title, or on its own line below it when both do not fit."""

    def lay(_event=None) -> None:
        meta.pack_forget()
        if top.winfo_width() >= title.winfo_reqwidth() + meta.winfo_reqwidth() + 8:
            meta.pack(in_=top, side="right", padx=4)
        else:
            meta.pack(after=top, anchor="w")

    top.bind("<Configure>", lay, add="+")
    lay()


def _gem(canvas: tk.Canvas, state: str) -> None:
    rows = HOLLOW if state == "new" else DIAMOND
    colour = {"answering": BRIGHT, "busy": BRIGHT, "thinking": GROK, "idle": DIM}.get(state, GROK)
    for y, line in enumerate(rows):
        for x, bit in enumerate(line):
            if bit == "1":
                shade = "#ffffff" if state in ("answering", "busy") and (x, y) == (2, 1) else colour
                canvas.create_rectangle(1 + x * PX, 1 + y * PX, x * PX + PX, y * PX + PX, fill=shade, width=0)
