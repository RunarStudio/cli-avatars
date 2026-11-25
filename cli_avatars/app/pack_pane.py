"""CONTEXT-PACKS in the chat dock: the pack cue when a chat starts with the pack, the satchel on the room pin."""

from __future__ import annotations

from types import SimpleNamespace

import context_packs
import focus
from cli_avatars.app import cues


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

