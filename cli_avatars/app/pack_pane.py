"""CONTEXT-PACKS in the chat dock: the pack cue when a chat starts with the pack, the satchel on the room pin."""

from __future__ import annotations

import time
from types import SimpleNamespace

import context_packs
import focus
from cli_avatars.app import cues
from cli_avatars.app.tasks_view import summary_age
from registry import task_chats

PIN_S = 1.0


def started(directory, config, request) -> None:
    """Play ``pack`` when the run's stdin starts with the pack; silent while a task is in focus."""
    if not str(getattr(request, "preamble", "")).startswith(context_packs.HEAD):
        return
    if focus.current(directory) is None:
        cues.play(SimpleNamespace(config=config), "pack")


def pin_title(pane, card: dict) -> str:
    """The room pin's title; the satchel shows beside it when a chat of the card started with its pack."""
    directory = pane.window.directory()
    rooms = [c["room"] for c in card.get("chats") or []]
    packed = any(context_packs.started_with(directory, room) for room in rooms)
    label = pane._pin_title
    mark = getattr(pane, "_pack_icon", None)
    if mark is not None and mark.master is not label.master:  # the pane was mounted again
        mark = pane._pack_icon = None
    if packed and mark is None:
        from cli_avatars.app import pack_art  # Tk only once a pin is drawn

        mark = pane._pack_icon = pack_art.icon(label.master, label.cget("bg"), scale=1)
    if mark is not None:
        if packed and not mark.winfo_manager():
            mark.pack(side="left", padx=(0, 4), before=label)
        elif not packed and mark.winfo_manager():
            mark.pack_forget()
    return f"WHERE WE ARE · {card['title'][:28]}"


def pin_refresh(pane, force: bool = False) -> None:
    """ROOM pin: pin the room's task summary over the thread; read at most once a second, widgets kept in place."""
    import tkinter as tk

    now = time.monotonic()
    if pane._pin_box is None or (not force and now < pane._pin_next):
        return
    pane._pin_next = now + PIN_S
    try:
        card = task_chats.room_task(pane.window.directory(), pane.room_id) if pane.room_id else None
    except OSError:
        return
    try:
        if card is None:
            pane._pin_box.pack_forget()
            return
        title = pin_title(pane, card)
        for label, text in ((pane._pin_title, title), (pane._pin_text, task_chats.pin_text(card)),
                            (pane._pin_age, summary_age(card.get("summary_at")))):
            if label.cget("text") != text:
                label.config(text=text)
        if not pane._pin_box.winfo_manager():
            pane._pin_box.pack(fill="x", padx=8, pady=(4, 0), after=pane.window._header)
    except (tk.TclError, AttributeError):
        return
