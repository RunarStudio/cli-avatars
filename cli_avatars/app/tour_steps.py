"""START-SETUP.1 CHAT: the first-run tour's steps and its once-only store. No Tk.

``ui/tour.json`` holds ``{"seen": true}`` after the tour ends or is skipped; Help → Take the tour replays it.
Each step names the widget it points at (``target``, an attribute path resolved on the app by ``tour``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

STORE = "ui/tour.json"


@dataclass(frozen=True)
class Step:
    key: str
    target: str
    title: str
    text: str


STEPS = (
    Step("chat", "_chat_btn", "Reach a chat",
         "Chat opens the chat on the room you used last. Clicking an avatar on the map opens its chat too."),
    Step("new_chat", "_new_chat_btn", "Make a new chat",
         "New chat: pick a topic, the CLI and, if you like, a task, then Start. Your recent chats are one click "
         "there too. Right-click a room on the map for the same card."),
    Step("rooms", "dungeon._left", "Your rooms",
         "Sessions and every topic live here, on the left. Click a topic to open its chat."),
    Step("to_line", "_chat_window._to_btn", "Who you are talking to",
         "To: avatar · room · CLI. Hover it for what each part means; click it to pick another orchestrator."),
    Step("summon", "dungeon._sessions.summon_btn", "Summon",
         "Summon puts the main orchestrator on the throne and starts it in one click."),
    Step("start_check", "_bootcheck_label", "Start check",
         "Click here to see what is ready and to set up what is missing."),
)


def due(directory: Path | str) -> bool:
    """True until the tour was seen once."""
    try:
        raw = json.loads((Path(directory) / STORE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not (isinstance(raw, dict) and raw.get("seen") is True)


def mark_seen(directory: Path | str) -> None:
    path = Path(directory) / STORE
    if path.is_symlink():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"seen": True}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return
