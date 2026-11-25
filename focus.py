"""FOCUS: one task in focus, or none; alerts for every other task wait until focus ends. No Tk.

``focus.json`` in the data dir holds the card, its title and topic, when focus began and the held alerts, so
all of it survives a restart. ``gate`` splits a needs-you list (``needs_you.pending``): the focused task's rows
(the card, or one of its task chats) pass at once; other rows that changed after focus began are held, one per
key; older ones just stay out of sight. ``leave`` ends focus and returns the held rows once, oldest first.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from events import EventRejected, directory_lock

STORE_NAME = "focus.json"
KEEP = 200
ROW_KEYS = ("key", "kind", "ts", "changed", "title", "room", "card")
_CARD = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_NONE = {"task": None, "title": "", "topic": "", "since": 0.0, "held": {}}


def load(directory: Path | str) -> dict:
    """The stored state; no focus when the file is missing or malformed."""
    try:
        data = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_NONE, held={})
    task = data.get("task") if isinstance(data, dict) else None
    if not isinstance(task, str) or not _CARD.fullmatch(task):
        return dict(_NONE, held={})
    held = data.get("held") if isinstance(data.get("held"), dict) else {}
    return {"task": task, "title": str(data.get("title") or ""), "topic": str(data.get("topic") or ""),
            "since": float(data.get("since") or 0.0),
            "held": {k: v for k, v in held.items() if isinstance(v, dict) and set(ROW_KEYS) <= set(v)}}


def current(directory: Path | str) -> str | None:
    return load(directory)["task"]


def held(directory: Path | str) -> list[dict]:
    """The held rows, oldest first."""
    return _oldest(load(directory)["held"].values())


def public(directory: Path | str) -> dict:
    """What the page and the Dungeon show: the task, its title, how many alerts wait."""
    state = load(directory)
    return {"task": state["task"], "title": state["title"], "topic": state["topic"], "waiting": len(state["held"])}


def stamp(directory: Path | str) -> tuple:
    try:
        st = (Path(directory) / STORE_NAME).stat()
    except OSError:
        return ()
    return (st.st_mtime_ns, st.st_size)


def start(directory: Path | str, task: object, now: float | None = None) -> bool:
    """Focus on card ``task``; False for a malformed id or no such card. Switching keeps what other tasks hold."""
    if not isinstance(task, str) or not _CARD.fullmatch(task):
        return False
    from registry.facade import Registry

    try:
        card = Registry(directory, timeout=0.2).task_get(task)
    except (EventRejected, OSError):
        return False
    if card is None:
        return False
    with directory_lock(Path(directory)):
        state = load(directory)
        kept = {k: v for k, v in state["held"].items() if not belongs(v, task)}
        _save(directory, {"task": task, "title": str(card.get("title") or ""), "topic": str(card.get("topic") or ""),
                          "since": time.time() if now is None else float(now), "held": kept})
    return True


def leave(directory: Path | str) -> list[dict]:
    """End focus; the held rows, oldest first, handed out this once."""
    root = Path(directory)
    with directory_lock(root):
        state = load(root)
        if state["task"] is None:
            return []
        _save(root, dict(_NONE, held={}))
    return _oldest(state["held"].values())


def belongs(row: dict, task: str | None) -> bool:
    """A row is the task's when it names the card or sits in one of the card's task chats."""
    if not task:
        return False
    room = row.get("room")
    return row.get("card") == task or (isinstance(room, str) and room.startswith(f"task-{task[:8]}-"))


def gate(directory: Path | str, items: list[dict]) -> tuple[list[dict], int]:
    """The rows to show now and how many alerts wait; new rows of other tasks are held as a side effect."""
    state = load(directory)
    task = state["task"]
    if task is None:
        return list(items), 0
    fresh = {r["key"]: r for r in items if not belongs(r, task) and r["changed"] > state["since"]}
    if any(k not in state["held"] or state["held"][k]["changed"] < r["changed"] for k, r in fresh.items()):
        with directory_lock(Path(directory)):
            state = load(directory)
            if state["task"] == task:
                for key, row in fresh.items():
                    first = state["held"].get(key, row)
                    state["held"][key] = {**{k: row[k] for k in ROW_KEYS}, "ts": min(first["ts"], row["ts"])}
                state["held"] = dict(sorted(state["held"].items(), key=lambda kv: kv[1]["changed"])[-KEEP:])
                _save(directory, state)
    return [r for r in items if belongs(r, task)], len(state["held"])


def room_of(rooms: list[dict], topic: str | None, home: str) -> str:
    """The room a task lives in: its topic's session room, else a room built with that topic, else ``home``."""
    named = [r for r in rooms if isinstance(r, dict) and not r.get("corridor") and r.get("name")]
    if topic and any(r["name"] == topic for r in named):
        return topic
    return next((r["name"] for r in named if r.get("custom") and topic and r.get("topic") == topic), home)


def _oldest(rows) -> list[dict]:
    return sorted((dict(r) for r in rows), key=lambda r: (r["ts"], r["key"]))


def _save(directory: Path | str, state: dict) -> None:
    root = Path(directory)
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("focus store is a symlink")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)
