"""CHAT-CTX.1: one CLI session per task per CLI (Claude, Grok, Cursor), so each conversation knows its task. No Tk.

A task is the card a task chat belongs to (every chat room of that card shares it), else the topic room itself.
``task_sessions.json`` in the data dir keeps, per task and CLI, the session id the CLI reported, when it started,
when it last answered and how many turns it had. ``drop`` (New session) clears one CLI; the next send starts fresh,
with the task's context pack. A room id from before this store (``room_chat/<room>.json``) is still resumed.
Nothing here starts a process; ids are checked against the runner's session UUID pattern before they are kept.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from board.model import CHAT_CLIS
from cli_avatars.model.room_stream import SESSION_ID_RE
from events import EventRejected, directory_lock

STORE_NAME = "task_sessions.json"
MAX_TASKS = 500


def key(directory: Path | str, room: str) -> str:
    """``card:<id>`` for a task chat room, else ``room:<room>``."""
    from registry import task_chats

    card = task_chats.task_for(directory, room)
    return f"card:{card['id']}" if card is not None else f"room:{room}"


def session(directory: Path | str, room: str, cli: str) -> str | None:
    """The session ``cli`` resumes for the task of ``room``; ``None`` starts a new one."""
    entry = _load(directory).get(key(directory, room), {}).get(cli)
    if entry is not None:
        return entry.get("id")
    from cli_avatars.model.room import load_room

    try:
        legacy = load_room(directory, room).session_id(cli)
    except (EventRejected, OSError):
        return None
    return legacy if isinstance(legacy, str) and SESSION_ID_RE.fullmatch(legacy) else None


def remember(directory: Path | str, room: str, cli: str, session_id: str) -> None:
    """Keep the id a CLI reported after a turn; a new id starts the count again."""
    if cli not in CHAT_CLIS or not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
        return
    task, now = key(directory, room), time.time()

    def change(entry: dict) -> dict:
        if entry.get("id") != session_id:
            entry = {"id": session_id, "started": now, "turns": 0}
        return {**entry, "at": now, "turns": int(entry.get("turns") or 0) + 1}

    _change(directory, task, cli, change)


def drop(directory: Path | str, room: str, cli: str) -> None:
    """New session: forget ``cli``'s session for this task (and the room's own id)."""
    from cli_avatars.model.room import set_session_id

    if cli not in CHAT_CLIS:
        return
    _change(directory, key(directory, room), cli, lambda _entry: {"id": None, "at": time.time()})
    try:
        set_session_id(directory, room, cli, None)
    except (EventRejected, OSError):
        pass


def listing(directory: Path | str, room: str) -> dict[str, dict]:
    """The live sessions of the task of ``room``, by CLI."""
    return _live(_load(directory).get(key(directory, room), {}))


def for_card(directory: Path | str, card_id: str, data: dict | None = None) -> list[dict]:
    """The card's live sessions for the phone: CLI, turns, started and last answer; never the id."""
    entries = _live((data if data is not None else _load(directory)).get(f"card:{card_id}", {}))
    return [{"cli": cli, "turns": e["turns"], "started": e["started"], "at": e["at"]} for cli, e in entries.items()]


def load(directory: Path | str) -> dict:
    """Every task's entries, for a caller that lists many cards."""
    return _load(directory)


def _live(entries: dict) -> dict[str, dict]:
    return {cli: entries[cli] for cli in CHAT_CLIS if cli in entries and entries[cli].get("id")}


def _load(directory: Path | str) -> dict:
    try:
        raw = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tasks = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, dict):
        return {}
    out = {}
    for task, entries in tasks.items():
        if not isinstance(task, str) or not isinstance(entries, dict):
            continue
        clean = {cli: _entry(entries[cli]) for cli in CHAT_CLIS if isinstance(entries.get(cli), dict)}
        out[task] = {cli: e for cli, e in clean.items() if e is not None}
    return out


def _entry(raw: dict) -> dict | None:
    sid = raw.get("id")
    if sid is not None and not (isinstance(sid, str) and SESSION_ID_RE.fullmatch(sid)):
        return None
    number = lambda name: float(raw[name]) if isinstance(raw.get(name), (int, float)) else 0.0  # noqa: E731
    return {"id": sid, "started": number("started"), "at": number("at"), "turns": int(number("turns"))}


def _change(directory: Path | str, task: str, cli: str, fn) -> None:
    root = Path(directory)
    with directory_lock(root):
        data = _load(directory)
        entries = data.setdefault(task, {})
        entries[cli] = fn(dict(entries.get(cli) or {}))
        newest = sorted(data.items(), key=lambda kv: max((e.get("at") or 0 for e in kv[1].values()), default=0))
        tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
        if tmp.is_symlink() or path.is_symlink():
            raise OSError("session store is a symlink")
        tmp.write_text(json.dumps({"tasks": dict(newest[-MAX_TASKS:])}), encoding="utf-8")
        os.replace(tmp, path)
