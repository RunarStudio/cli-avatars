"""GROK-CHAT: Grok conversations side by side: one row per room, task or Grok topic with its own session. No Tk.

Rows come from the Grok sessions in ``task_sessions.json`` (a room's, or a task's) and from the Grok topics Daniel
made with **+ New Grok topic** (``grok_topics.json`` in the data dir, never in git). A Grok topic is a topic room of
its own, so it keeps its own history and session; it is bound to the room (or task chat) it was made from and works
in that room's folder, read at launch and never copied, the way a task chat works in its card topic's folder.
Live state comes from ``GrokBuildSource`` (``~/.grok/sessions``, which never opens auth or chat history files).
Nothing here starts a process; session ids stay on the PC (rows carry no id).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

from events import EventRejected, directory_lock

STORE_NAME = "grok_topics.json"
MAX_TOPICS = 60
MAX_ROWS = 40
LAST_LIMIT = 90


def new_topic(directory: Path | str, bound: str, now: float | None = None) -> str:
    """Daniel's **+ New Grok topic**: a topic room bound to ``bound`` (a room or task chat). Starts nothing."""
    from cli_avatars.model.room import add_participant
    from topics import ensure_topic, get_topic, set_topic, valid_topic_id

    if not valid_topic_id(bound):
        raise EventRejected("schema")
    parent = get_topic(directory, bound) or {}
    now = time.time() if now is None else now
    root = Path(directory)
    with directory_lock(root):
        data = _load(directory)
        if len(data) >= MAX_TOPICS:
            raise EventRejected("full")
        n = 1 + max((int(v.get("n") or 0) for v in data.values()), default=0)
        room = f"grok-{n}"
        data[room] = {"bound": bound, "n": n, "created": now}
        _save(root, data)
    ensure_topic(directory, room, ts=now)
    title = f"Grok {n} · {parent.get('title') or bound}"[:80]
    project = parent.get("project") if isinstance(parent.get("project"), str) and parent.get("project") else None
    set_topic(directory, room, title=title, status="open", project=project, ts=now)
    add_participant(directory, room, "grok")
    return room


def bound_to(directory: Path | str, room: str) -> str | None:
    entry = _load(directory).get(room)
    return entry["bound"] if entry else None


def with_folder(directory: Path | str, room):
    """A Grok topic without its own folder works in its bound room's (Daniel picked it there). Not stored."""
    from cli_avatars.model.room import load_room
    from registry import task_chats

    parent = bound_to(directory, room.room_id) if not room.working_dir else None
    if parent is None:
        return room
    try:
        folder = task_chats.with_folder(directory, load_room(directory, parent)).working_dir
    except (EventRejected, OSError):
        return room
    return replace(room, working_dir=folder) if folder else room


def rows(directory: Path | str, live: dict[str, str] | None = None, running=None) -> list[dict]:
    """Every Grok conversation, newest first: room, kind, title, last line, time, turns, state. No session id."""
    from cli_avatars.app import task_sessions
    from registry.facade import Registry

    live = grok_live() if live is None else live
    found: dict[str, dict] = {}
    registry = None
    for key, entries in task_sessions.load(directory).items():
        entry = entries.get("grok")
        if not entry or not entry.get("id"):
            continue
        kind, ident = key.split(":", 1)
        room = ident
        if kind == "card":
            registry = registry or Registry(directory)
            card = registry.task_get(ident) or {}
            chats = card.get("chats") or []
            pick = next((c for c in reversed(chats) if c.get("cli") == "grok"), chats[-1] if chats else None)
            if pick is None:
                continue
            room = pick["room"]
        found[room] = {"room": room, "kind": "task" if kind == "card" else "room", "at": entry["at"],
                       "turns": entry["turns"], "sid8": entry["id"][:8]}
    for room, entry in _load(directory).items():
        row = found.setdefault(room, {"room": room, "at": entry["created"], "turns": 0, "sid8": ""})
        row["kind"] = "topic"
    out = []
    for row in sorted(found.values(), key=lambda r: -r["at"])[:MAX_ROWS]:
        sid8 = row.pop("sid8")
        busy = bool(running and running(row["room"]))
        state = "answering" if busy else live.get(sid8, "idle") if sid8 else "new"
        out.append({**row, "title": _title(directory, row["room"]), "last": _last(directory, row["room"]),
                    "state": state, "live": busy or sid8 in live})
    return out


def grok_live() -> dict[str, str]:
    """Grok Build sessions changed in the last 15 minutes: first 8 characters of the id to busy/thinking/idle."""
    from sessions import GrokBuildSource

    try:
        return {info.agent_id: info.status for info in GrokBuildSource().scan()}
    except OSError:
        return {}


def _title(directory: Path | str, room: str) -> str:
    from cli_avatars.app.room_log import _topic_field

    return _topic_field(directory, room, "title") or room


def _last(directory: Path | str, room: str) -> str:
    from cli_avatars.app import room_log

    lines = [text for sender, text in room_log.history(directory, room, "grok", limit=12)
             if not text.startswith(("result:", "tool:"))]
    return lines[-1][:LAST_LIMIT] if lines else ""


def _load(directory: Path | str) -> dict[str, dict]:
    from topics import valid_topic_id

    try:
        raw = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    topics = raw.get("topics") if isinstance(raw, dict) else None
    if not isinstance(topics, dict):
        return {}
    out = {}
    for room, entry in topics.items():
        if valid_topic_id(room) and isinstance(entry, dict) and valid_topic_id(entry.get("bound")):
            created = entry.get("created")
            out[room] = {"bound": entry["bound"], "n": int(entry.get("n") or 0) if isinstance(entry.get("n"), int)
                         else 0, "created": float(created) if isinstance(created, (int, float)) else 0.0}
    return out


def _save(root: Path, data: dict) -> None:
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("grok topic store is a symlink")
    tmp.write_text(json.dumps({"topics": data}), encoding="utf-8")
    os.replace(tmp, path)
