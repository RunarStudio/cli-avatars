"""TASKBACK.5: one card tile of the Tasks board: badge, title, notes, meta, progress, the chat slip. No state.

``shape`` says which widgets a card needs; a card that keeps its shape is updated in place by ``refit``.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.tasks_card import GOLD, PARCH, WINE, badge
from cli_avatars.app.tasks_view import TaskCard, card_meta

_CARD = PARCH
_INK = "#2a1c10"
_DIM = "#6b5233"
_SLIP = "#4a1830"


def set_text(widget: tk.Widget, text: str) -> None:
    """Config only on a change, so an unchanged label is not redrawn."""
    if widget.cget("text") != text:
        widget.config(text=text)


def _chat_line(box: tk.Frame, card: TaskCard, open_chat) -> tk.Frame:
    """A wine speech slip: a pixel bubble, ``N chats · last reply``; a click opens that chat."""
    row = tk.Frame(box, bg=_SLIP, cursor="hand2")
    row.pack(fill="x", padx=6, pady=(1, 3))
    icon = tk.Canvas(row, width=11, height=9, bg=_SLIP, highlightthickness=0, bd=0)
    icon.create_rectangle(1, 0, 10, 6, fill=_CARD, width=0)
    icon.create_rectangle(0, 1, 11, 5, fill=_CARD, width=0)
    icon.create_rectangle(2, 6, 4, 8, fill=_CARD, width=0)
    icon.create_rectangle(3, 2, 4, 3, fill=WINE, width=0)
    icon.create_rectangle(5, 2, 6, 3, fill=WINE, width=0)
    icon.create_rectangle(7, 2, 8, 3, fill=WINE, width=0)
    icon.pack(side="left", padx=(4, 3), pady=3)
    count = f"{card.chats} chat{'' if card.chats == 1 else 's'}"
    text = tk.Label(row, text=f"{count} · {card.last_reply or 'no reply yet'}", bg=_SLIP, fg=_CARD,
                    font="DungeonBubble", anchor="w", justify="left", wraplength=170)
    text.pack(side="left", fill="x", expand=True, padx=(0, 4))
    row.text = text
    text.bind("<Configure>", lambda e: text.config(wraplength=max(60, e.width - 4)))
    for widget in (row, icon, text):
        widget.bind("<ButtonRelease-1>", lambda e, r=card.chat_room: open_chat(r, False))
    return row


def card_tile(parent, card: TaskCard, open_chat=lambda room, new: None) -> tk.Frame:
    box = tk.Frame(parent, bg=_CARD, highlightthickness=1, highlightbackground="#8a6a3a", cursor="hand2",
                   takefocus=1, highlightcolor=GOLD)
    box.pack(fill="x", pady=2)
    tags = tk.Frame(box, bg=_CARD)
    tags.pack(fill="x", padx=6, pady=(4, 0))
    badge(tags, card.column).pack(side="left")
    if card.decisions:
        decide_tag(tags, card.decisions).pack(side="left", padx=(4, 0))
    parts = box.parts = {}
    parts["title"] = title = tk.Label(box, text=card.title, bg=_CARD, fg=_INK, font="DungeonText", anchor="w",
                                      justify="left", wraplength=180)
    title.pack(fill="x", padx=6, pady=(4, 0))
    title.bind("<Configure>", lambda e: title.config(wraplength=max(60, e.width - 4)))
    for key, colour in (("note", _DIM), ("learnt", "#2f5a2e")):
        text = _texts(card)[key]
        if text:
            parts[key] = line = tk.Label(box, text=text, bg=_CARD, fg=colour, font="DungeonBubble", anchor="w",
                                         justify="left", wraplength=180)
            line.pack(fill="x", padx=6)
            line.bind("<Configure>", lambda e, w=line: w.config(wraplength=max(60, e.width - 4)))
    parts["meta"] = meta = tk.Label(box, text=card_meta(card), bg=_CARD, fg=_DIM, font="DungeonBubble", anchor="w",
                                    justify="left", wraplength=180)
    meta.pack(fill="x", padx=6, pady=(0, 2 if card.progress is not None else 4))
    meta.bind("<Configure>", lambda e: meta.config(wraplength=max(60, e.width - 4)))
    if card.progress is not None:
        parts["bar"] = bar = tk.Canvas(box, height=4, bg="#b8a47c", highlightthickness=0, bd=0)
        bar.pack(fill="x", padx=6, pady=(0, 5))
        bar.fill = bar.create_rectangle(0, 0, 0, 4, fill=WINE, width=0)
        bar.progress = card.progress
        bar.bind("<Configure>", lambda e: bar.coords(bar.fill, 0, 0, e.width * bar.progress // 100, 4))
    box.chat_line = _chat_line(box, card, open_chat) if card.chats else None
    box.shape = shape(card)
    return box


def shape(card: TaskCard) -> tuple:
    """What decides a card's widgets; two cards of one shape differ only in text, so a refit is enough."""
    return (card.title, card.column, card.decisions, bool(card.status_note), bool(card.learnt),
            card.progress is None, bool(card.chats), card.chat_room)


def _texts(card: TaskCard) -> dict[str, str]:
    return {"note": card.status_note, "learnt": card.learnt and f"learnt: {card.learnt}", "meta": card_meta(card)}


def refit(box: tk.Frame, card: TaskCard) -> None:
    """Update a card of the same ``shape`` in place: changed texts and the progress bar only."""
    parts = box.parts
    for key, text in _texts(card).items():
        if key in parts:
            set_text(parts[key], text)
    bar = parts.get("bar")
    if bar is not None and bar.progress != card.progress:
        bar.progress = card.progress
        bar.coords(bar.fill, 0, 0, bar.winfo_width() * card.progress // 100, 4)
    if box.chat_line is not None:
        count = f"{card.chats} chat{'' if card.chats == 1 else 's'}"
        set_text(box.chat_line.text, f"{count} · {card.last_reply or 'no reply yet'}")


def decide_tag(parent, count: int) -> tk.Frame:
    """A gold tag with a wine gem: this card waits on Daniel's decision."""
    box = tk.Frame(parent, bg="#1a1012")
    inner = tk.Frame(box, bg=GOLD)
    inner.pack(padx=(0, 1), pady=(0, 1))
    gem = tk.Canvas(inner, width=6, height=6, bg=GOLD, highlightthickness=0, bd=0)
    gem.create_polygon(3, 0, 6, 3, 3, 6, 0, 3, fill=WINE, width=0)
    gem.pack(side="left", padx=(3, 2))
    text = "DECIDE" if count == 1 else f"DECIDE ×{count}"
    tk.Label(inner, text=text, bg=GOLD, fg=_INK, font="DungeonBubble", padx=0, pady=0).pack(side="left", padx=(0, 4))
    return box
