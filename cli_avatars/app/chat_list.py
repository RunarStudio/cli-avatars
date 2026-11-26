"""GROK-ORCH.1: every chat Daniel had in the app, newest first and by project, to reopen and resume. No Tk.

A chat is a topic room: one a CLI joined (New chat, a task chat, a Grok topic, Summon), one with a stored session, or
an Inbox-only room (``cli`` empty). Each row names its CLI (the one that answered last), whether the next send resumes
its session (``task_sessions.json``, ``-r`` for Grok) and when it was last touched. Everything comes from files in the
data dir, so the list survives a restart. Rows never carry a session id or a path. Nothing here starts a process.
"""

from __future__ import annotations

from pathlib import Path

from board.model import CHAT_CLIS
from events import EventRejected

NO_PROJECT = "No project"
MAX_ROWS = 200


def rows(directory: Path | str) -> list[dict]:
    """``room``, ``title``, ``project``, ``kind`` (task, grok, chat), ``cli``, ``resumes``, ``turns``, ``at``."""
    from cli_avatars.app import task_sessions
    from cli_avatars.app.projects_view import _cards
    from cli_avatars.model.room import load_room
    from topics import list_topics

    try:
        topics = list_topics(directory, timeout=0.3)
    except (EventRejected, OSError):
        return []
    try:
        cards = {chat["room"]: card for card in _cards(directory) for chat in card.get("chats") or ()}
    except (EventRejected, OSError):
        cards = {}
    sessions = task_sessions.load(directory)
    out = []
    for topic in topics:
        room = str(topic["id"])
        card = cards.get(room)
        entries = {cli: e for cli, e in sessions.get(f"card:{card['id']}" if card else f"room:{room}", {}).items()
                   if e.get("id")}
        try:
            joined = [cli for cli in CHAT_CLIS if cli in load_room(directory, room).participants]
        except (EventRejected, OSError, ValueError):
            joined = []
        cli = max(entries, key=lambda c: entries[c]["at"]) if entries else joined[0] if joined else ""
        entry = entries.get(cli) or {}
        touched = float(topic.get("updated") or topic.get("created") or 0)
        out.append({"room": room, "title": str(topic.get("title") or room),
                    "project": str(topic.get("project") or (card or {}).get("project") or ""),
                    "kind": "task" if card else "grok" if room.startswith("grok-") else "chat", "cli": cli,
                    "resumes": bool(entry), "turns": int(entry.get("turns") or 0),
                    "at": max(touched, float(entry.get("at") or 0))})
    out.sort(key=lambda r: -r["at"])
    return out[:MAX_ROWS]


def by_project(found: list[dict]) -> list[tuple[str, list[dict]]]:
    """``(project, rows)``: the project with the newest chat first, chats with no project last."""
    groups: dict[str, list[dict]] = {}
    for row in found:
        groups.setdefault(row["project"] or NO_PROJECT, []).append(row)
    return sorted(groups.items(), key=lambda kv: (kv[0] == NO_PROJECT, -kv[1][0]["at"]))
