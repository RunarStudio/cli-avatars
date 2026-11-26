"""START-SETUP.1 CHAT: what the New chat card lists and what Start writes. No Tk, and nothing here starts a CLI.

Start makes or reuses a topic and joins the picked CLI to its room chat, the way the Sessions panel does; with a task
it is that card's task chat (``task_chats.start_chat``, which brings the context pack). The CLI starts only on
Daniel's Enter in the chat.
"""

from __future__ import annotations

import re
from pathlib import Path

from board.model import CHAT_CLIS
from events import EventRejected

RECENT = 6
MAX_TASKS = 40


def recent(directory: Path | str, limit: int = RECENT) -> list[dict]:
    """The chats touched last, newest first: ``id``, ``title``, ``project``."""
    from topics import list_topics

    try:
        rows = list_topics(directory, timeout=0.3)
    except (EventRejected, OSError):
        return []
    rows = sorted(rows, key=lambda t: float(t.get("updated") or t.get("created") or 0), reverse=True)
    return [{"id": str(t["id"]), "title": str(t.get("title") or t["id"]), "project": str(t.get("project") or "")}
            for t in rows[:limit]]


def topic_choices(directory: Path | str) -> list[tuple[str, str]]:
    """Every topic as ``(id, title)``, in the topic list's order."""
    from topics import list_topics

    try:
        return [(str(t["id"]), str(t.get("title") or t["id"])) for t in list_topics(directory, timeout=0.3)]
    except (EventRejected, OSError):
        return []


def tasks(directory: Path | str) -> list[tuple[str, str]]:
    """Open cards as ``(id, title)``, newest first, for the optional task."""
    from registry.facade import Registry

    registry = Registry(directory)
    root = registry.store.root
    if not root.is_dir() or root.is_symlink():
        return []
    found = []
    for project in sorted(p.name for p in root.iterdir() if p.is_dir()):
        try:
            found.extend(registry.task_list(project))
        except (EventRejected, OSError):
            continue
    found = sorted((c for c in found if c.get("column") != "done"), key=lambda c: c.get("updated") or 0, reverse=True)
    return [(c["id"], c["title"]) for c in found[:MAX_TASKS]]


def slug(title: str) -> str:
    """A topic id from a typed name: ``Moon Garden`` → ``moon-garden``; ``""`` when nothing usable is left."""
    from topics import valid_topic_id

    text = re.sub(r"[^a-z0-9._-]+", "-", str(title or "").lower()).strip(".-")[:64].strip(".-")
    return text if text and valid_topic_id(text) else ""


def start(directory: Path | str, *, topic: str, title: str, project: str, cli: str, card: str = "") -> tuple[str, str]:
    """Daniel's Start: ``(room, "")``, else ``("", why)``. Writes the topic, room and card files only."""
    from cli_avatars.model.room import add_participant
    from topics import ensure_topic, set_topic

    if cli not in CHAT_CLIS:
        return "", "Pick Claude, Grok or Cursor."
    if card:
        from registry import task_chats
        from registry.facade import Registry

        ready, why = task_chats.cli_ready(cli)
        if not ready:
            return "", why
        try:
            return task_chats.start_chat(Registry(directory), card, cli)[1]["room"], ""
        except (EventRejected, OSError):
            return "", "That task's chat was not stored."
    room = topic or slug(title)
    if not room:
        return "", "Name the new topic with a letter or a digit, or pick one."
    try:
        ensure_topic(directory, room, title=title.strip() or None)
        if project.strip() and not topic:
            set_topic(directory, room, project=project.strip())
        add_participant(directory, room, cli)
    except (EventRejected, OSError):
        return "", "The chat was not stored."
    return room, ""
