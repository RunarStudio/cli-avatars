"""QUICK-CAPTURE: Ctrl+Space opens a capture strip inside the Dungeon window (no new window).

One text line, the suggested topic with two alternates as chips (Tab picks the next), a Card / Chat
toggle; Enter saves through ``registry.capture`` as Daniel, Esc closes. The new card lands on the Board
in place and the ``capture`` cue plays. A chat capture opens its task chat; no CLI starts until Enter there.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.tasks_card import GOLD, PARCH, WINE
from events import EventRejected
from registry import capture

HOTKEY = "<Control-space>"
CHIPS = 3
TOAST_MS = 2200
_BG = "#1a1218"
_CHIP = "#2e2230"
_INK = "#2a1c10"
_DIM = "#9a8a70"
_ERR = "#ff8a70"
_WHY = {"empty": "Write the thought first.", "missing": "That topic is gone; pick another.",
        "timeout": "The board is busy; try again."}


class CaptureStrip:
    """Owned by ``DungeonWindow``; built on first open, then shown and hidden in place."""

    def __init__(self, view) -> None:
        self.view = view
        self.frame: tk.Frame | None = None
        self.chips: list[tk.Button] = []
        self.picked = ""
        self.as_chat = False
        self._manual = False
        self._index = None
        self._fallback = ""
        self._toast_job = None

    def is_open(self) -> bool:
        return self.frame is not None and bool(self.frame.winfo_manager())

    def open(self, _event=None) -> str:
        if self.frame is None:
            self._build()
        directory = self.view.app._chat_directory()
        self._fallback = _filter_topic(self.view.app)
        try:
            self._index = capture.build_index(directory)
        except (EventRejected, OSError):
            self._index = capture.CaptureIndex({}, {})
        self._manual = False
        self.entry.delete(0, "end")
        self.error.config(text="")
        self._set_mode(False)
        self._rank()
        self.toast.place_forget()
        self.frame.place(in_=self.view._mid, relx=0.5, y=36, anchor="n", relwidth=0.72)
        self.frame.lift()
        self.entry.focus_set()
        return "break"

    def close(self, _event=None) -> str:
        if self.frame is not None:
            self.frame.place_forget()
        return "break"

    def save(self, _event=None) -> str:
        app = self.view.app
        try:
            card, room = capture.capture(app._chat_directory(), self.entry.get(), self.picked, self.as_chat)
        except EventRejected as exc:
            self.error.config(text=_WHY.get(exc.reason, "The board refused that thought."))
            return "break"
        except OSError:
            self.error.config(text="The board file could not be written.")
            return "break"
        self.close()
        _cue(app, "capture")
        panel = getattr(app, "_tasks_panel", None)
        if panel is not None:
            panel.refresh(force=True)
            panel.flash(card["id"])
        if room is not None:
            from cli_avatars.app.tasks_panel import open_task_chat

            open_task_chat(app, room, False)
        where = self._index.title(self.picked) if self._index else self.picked
        self._show_toast(f"✓ {'Chat' if room else 'Card'} saved in {where}")
        return "break"

    def pick(self, topic: str) -> None:
        self.picked, self._manual = topic, True
        self._paint_chips(self._ranked)
        self.entry.focus_set()

    def _next(self, _event=None) -> str:
        """Tab: the next chip's topic."""
        shown = [chip.topic for chip in self.chips]
        if shown:
            at = shown.index(self.picked) if self.picked in shown else -1
            self.pick(shown[(at + 1) % len(shown)])
        return "break"

    def _rank(self, _event=None) -> None:
        if self._index is None or (_event is not None and getattr(_event, "keysym", "") in ("Tab", "Escape")):
            return
        self._ranked = self._index.rank(self.entry.get(), self._fallback) or [self._fallback]
        if not self._manual or self.picked not in self._ranked:
            self.picked, self._manual = self._ranked[0], False
        self._paint_chips(self._ranked)

    def _paint_chips(self, ranked: list[str]) -> None:
        shown = ranked[:CHIPS] if self.picked in ranked[:CHIPS] else [self.picked, *ranked[:CHIPS - 1]]
        for chip, topic in zip(self.chips, shown, strict=False):
            on = topic == self.picked and bool(topic)
            label = self._index.title(topic) if self._index and topic else "no topic"
            text = f"{label}  ✓" if on else label
            if chip.cget("text") != text:
                chip.config(text=text)
            chip.config(bg=GOLD if on else _CHIP, fg=_INK if on else GOLD, command=lambda t=topic: self.pick(t))
            chip.topic = topic
            if not chip.winfo_manager():
                chip.pack(side="left", padx=(0, 6))
        for chip in self.chips[len(shown):]:
            chip.pack_forget()

    def _set_mode(self, chat: bool) -> None:
        self.as_chat = chat
        for button, on in ((self.card_btn, not chat), (self.chat_btn, chat)):
            button.config(bg=WINE if on else _CHIP, fg=PARCH if on else _DIM)
        self.entry.focus_set()

    def _show_toast(self, text: str) -> None:
        root = self.view.app.root
        self.toast.config(text=text)
        self.toast.place(in_=self.view._mid, relx=0.5, y=36, anchor="n")
        self.toast.lift()
        if self._toast_job is not None:
            root.after_cancel(self._toast_job)
        self._toast_job = root.after(TOAST_MS, self._hide_toast)

    def _hide_toast(self) -> None:
        self._toast_job = None
        self.toast.place_forget()

    def _build(self) -> None:
        mid = self.view._mid
        self.frame = frame = tk.Frame(mid, bg=_BG, highlightthickness=2, highlightbackground=GOLD,
                                      highlightcolor=GOLD)
        top = tk.Frame(frame, bg=_BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        _quill(top).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(top, bg=PARCH, fg=_INK, insertbackground=_INK, relief="flat", font="DungeonTitle",
                              highlightthickness=1, highlightbackground="#8a6a3a", highlightcolor=WINE)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        seg = tk.Frame(top, bg="#8a6a3a")
        seg.pack(side="left", padx=(8, 0))
        self.card_btn = _flat(seg, "Card", lambda: self._set_mode(False))
        self.card_btn.pack(side="left", padx=(1, 0), pady=1)
        self.chat_btn = _flat(seg, "Chat", lambda: self._set_mode(True))
        self.chat_btn.pack(side="left", padx=1, pady=1)
        row = tk.Frame(frame, bg=_BG)
        row.pack(fill="x", padx=10, pady=(2, 0))
        tk.Label(row, text="Topic", bg=_BG, fg=_DIM, font="DungeonBubble").pack(side="left", padx=(26, 8))
        self.chips = [_flat(row, "", None) for _ in range(CHIPS)]
        self._ranked: list[str] = []
        foot = tk.Frame(frame, bg=_BG)
        foot.pack(fill="x", padx=10, pady=(2, 6))
        tk.Label(foot, text="Enter saves · Tab next topic · Esc closes", bg=_BG, fg=_DIM,
                 font="DungeonBubble").pack(side="right")
        self.error = tk.Label(foot, text="", bg=_BG, fg=_ERR, font="DungeonBubble", anchor="w")
        self.error.pack(side="left", fill="x", expand=True, padx=(26, 0))
        self.toast = tk.Label(mid, text="", bg=WINE, fg=PARCH, font="DungeonText", padx=14, pady=5,
                              highlightthickness=1, highlightbackground=GOLD)
        self.entry.bind("<Return>", self.save)
        self.entry.bind("<KP_Enter>", self.save)
        self.entry.bind("<Escape>", self.close)
        self.entry.bind("<Tab>", self._next)
        self.entry.bind("<KeyRelease>", self._rank)
        frame.bind("<Escape>", self.close)


def mount(view) -> CaptureStrip:
    """The strip on ``view`` and its hotkey on the Dungeon root (every widget of the window gets it)."""
    strip = CaptureStrip(view)
    view.app.root.bind(HOTKEY, strip.open)
    return strip


def _filter_topic(app) -> str:
    """The Board filter's topic, else the chat's topic."""
    panel = getattr(app, "_tasks_panel", None)
    if panel is not None:
        return panel._edit_topic() or ""
    from cli_avatars.app.tasks_view import selected_topic

    return selected_topic(app)


def _flat(parent, text: str, command) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=_CHIP, fg=GOLD, activebackground=GOLD,
                     activeforeground=_INK, relief="flat", bd=0, highlightthickness=0, font="DungeonText",
                     padx=9, pady=2, cursor="hand2", takefocus=0)


def _quill(parent) -> tk.Canvas:
    """A pixel quill over a scrap of parchment."""
    art = tk.Canvas(parent, width=20, height=20, bg=_BG, highlightthickness=0, bd=0)
    art.create_rectangle(2, 12, 14, 19, fill=PARCH, width=0)
    art.create_rectangle(3, 14, 12, 15, fill="#8a6a3a", width=0)
    art.create_rectangle(3, 17, 9, 18, fill="#8a6a3a", width=0)
    for i, (x, y) in enumerate(((15, 1), (13, 3), (11, 5), (9, 7), (7, 9))):
        art.create_rectangle(x, y, x + 4, y + 3, fill="#f2ead8" if i % 2 else "#e0d4b8", width=0)
    art.create_rectangle(16, 2, 18, 4, fill=GOLD, width=0)
    art.create_rectangle(5, 11, 7, 13, fill=WINE, width=0)
    art.create_rectangle(4, 13, 5, 14, fill=_INK, width=0)
    return art


def _cue(app, name: str) -> None:
    from cli_avatars.app import cues

    cues.play(app, name)
