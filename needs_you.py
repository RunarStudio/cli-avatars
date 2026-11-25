"""NEEDS-YOU.1: what waits on Daniel, one list from the stores that already hold it. No Tk.

Sources: open decisions (``decisions.jsonl``), cards in ``blocked`` (the boards), replies to him in a
room after his last line there (the channel), room runs that ended after it (the boards' ``prompt``
events), and one ``mail`` row while letters wait in the Mailroom (``mailroom.py``). A reply and a run in the
same room are one item. Order: decision, blocked, reply, run, mail, then oldest first. Clearing stores the
item's last change in ``needs_you.json``; a newer change brings it back. Replies and runs older than
``FRESH_S`` drop out. Nothing read here is run.
"""

from __future__ import annotations

import json
import os
import re
import time
from calendar import timegm
from pathlib import Path

from events import CHANNEL_DIR_NAME, EventRejected, directory_lock, sanitize_text

KINDS = ("decision", "blocked", "reply", "run", "mail")
RANK = {kind: i for i, kind in enumerate(KINDS)}
STORE_NAME = "needs_you.json"
FRESH_S = 3 * 86400
TAIL_BYTES = 128 * 1024
DETAIL_LIMIT = 160
KEEP = 500
RUN_WORDS = {"ok": "Run finished", "error": "Run failed", "timeout": "Run timed out"}
_KEY = re.compile(r"^(decision|card|room|mail):[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def valid_key(key: object) -> bool:
    return isinstance(key, str) and _KEY.fullmatch(key) is not None


def merge(*sources, cleared: dict | None = None) -> list[dict]:
    """One row per key (the most urgent kind, the newest change), cleared rows out, urgency then oldest first."""
    best: dict[str, dict] = {}
    for rows in sources:
        for row in rows:
            have = best.get(row["key"])
            if have is None:
                best[row["key"]] = dict(row)
                continue
            top = row if RANK[row["kind"]] < RANK[have["kind"]] else have
            best[row["key"]] = {**top, "changed": max(have["changed"], row["changed"])}
    marks = cleared or {}
    found = [r for r in best.values() if not (r["key"] in marks and marks[r["key"]] >= r["changed"])]
    return sorted(found, key=lambda r: (RANK[r["kind"]], r["ts"], r["key"]))


def collect(directory: Path | str, now: float | None = None) -> list[dict]:
    """Every live item, cleared or not."""
    root = Path(directory)
    since = (time.time() if now is None else now) - FRESH_S
    replies, last_user = _replies(root, since)
    return merge(_decisions(root), _blocked(root), replies, _runs(root, since, last_user), _mail(root))


def pending(directory: Path | str, now: float | None = None) -> list[dict]:
    """The list Daniel sees: live items he has not cleared since their last change."""
    root = Path(directory)
    since = (time.time() if now is None else now) - FRESH_S
    replies, last_user = _replies(root, since)
    return merge(_decisions(root), _blocked(root), replies, _runs(root, since, last_user), _mail(root),
                 cleared=_load(root))


def clear(directory: Path | str, key: object, now: float | None = None) -> bool:
    """Clear one live item until it changes. False for an unknown or malformed key."""
    if not valid_key(key):
        return False
    root = Path(directory)
    item = next((r for r in collect(root, now) if r["key"] == key), None)
    if item is None:
        return False
    with directory_lock(root):
        marks = _load(root)
        marks[key] = item["changed"]
        kept = dict(sorted(marks.items(), key=lambda kv: kv[1])[-KEEP:])
        tmp = root / (STORE_NAME + ".tmp")
        tmp.write_text(json.dumps({"cleared": kept}), encoding="utf-8")
        os.replace(tmp, root / STORE_NAME)
    return True


def stamp(directory: Path | str) -> tuple:
    """Sizes and mtimes of the sources and the cleared store; it moves when the list may have."""
    root = Path(directory)
    paths = [root / "decisions.jsonl", root / STORE_NAME, root / "mailroom.json"]
    for pattern in (f"{CHANNEL_DIR_NAME}/*.jsonl", "board/*/events.jsonl", "board/*/cards"):
        try:
            paths.extend(sorted(root.glob(pattern)))
        except OSError:
            continue
    found = []
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            continue
        found.append((str(path.relative_to(root)), st.st_mtime_ns, st.st_size))
    return tuple(found)


def _load(root: Path) -> dict[str, float]:
    try:
        data = json.loads((root / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    marks = data.get("cleared") if isinstance(data, dict) else None
    if not isinstance(marks, dict):
        return {}
    return {k: float(v) for k, v in marks.items() if valid_key(k) and isinstance(v, (int, float))}


def _item(key: str, kind: str, ts: float, changed: float, title: str, detail: str, room, card) -> dict:
    return {"key": key, "kind": kind, "ts": ts, "changed": changed, "title": title,
            "detail": sanitize_text(detail, DETAIL_LIMIT), "room": room, "card": card}


def _decisions(root: Path) -> list[dict]:
    from decisions import list_decisions
    from registry.task_decisions import pending as on_cards

    try:
        rows = list_decisions(root, open_only=True)
        cards = {r["id"]: r for r in on_cards(root)}
    except (EventRejected, OSError):
        return []
    found = []
    for row in rows:
        card = cards.get(row["id"])
        if row.get("card") and card is None:
            continue
        title = card["title"] if card else _topic_title(root, str(row["room"]))
        found.append(_item(f"decision:{row['id']}", "decision", float(row["ts"]), float(row["ts"]), title,
                           str(row["question"]), row["room"], row.get("card")))
    return found


def _mail(root: Path) -> list[dict]:
    import mailroom

    return mailroom.needs_row(root)


def _blocked(root: Path) -> list[dict]:
    from registry.facade import Registry

    registry = Registry(root)
    base = registry.store.root
    if not base.is_dir() or base.is_symlink():
        return []
    found = []
    for project in sorted(p.name for p in base.iterdir() if p.is_dir()):
        try:
            cards = registry.task_list(project, column="blocked")
        except (EventRejected, OSError):
            continue
        for card in cards:
            at = _epoch(card["updated"])
            found.append(_item(f"card:{card['id']}", "blocked", at, at, card["title"],
                               card.get("status_note") or "Blocked", card.get("topic"), card["id"]))
    return found


def _replies(root: Path, since: float) -> tuple[list[dict], dict[str, float]]:
    """Lines to Daniel after his last line in each room; also his last line's time per room."""
    base = root / CHANNEL_DIR_NAME
    if base.is_symlink() or not base.is_dir():
        return [], {}
    waiting: dict[str, list[dict]] = {}
    last_user: dict[str, float] = {}
    for path in sorted(base.glob("*.jsonl")):
        for obj in _tail(path, since):
            room, ts = obj.get("channel"), obj.get("ts")
            if not isinstance(room, str) or not valid_key(f"room:{room}") or not isinstance(ts, (int, float)):
                continue
            if obj.get("from") == "user":
                last_user[room] = max(last_user.get(room, 0.0), float(ts))
                waiting.pop(room, None)
                continue
            to = obj.get("to")
            if obj.get("kind") == "decision" or not (to == "user" or (isinstance(to, list) and "user" in to)):
                continue
            waiting.setdefault(room, []).append(obj)
    found = []
    for room, lines in waiting.items():
        if float(lines[-1]["ts"]) < since:
            continue
        found.append(_item(f"room:{room}", "reply", float(lines[0]["ts"]), float(lines[-1]["ts"]),
                           _topic_title(root, room), str(lines[-1].get("note") or ""), room, None))
    return found, last_user


def _runs(root: Path, since: float, last_user: dict[str, float]) -> list[dict]:
    """The newest ended room run per room, when Daniel wrote nothing there after it."""
    from board.model import validate_event

    newest: dict[str, dict] = {}
    for path in sorted((root / "board").glob("*/events.jsonl")):
        for raw in _tail_lines(path):
            try:
                event = validate_event(json.loads(raw))
            except (ValueError, RecursionError, EventRejected):
                continue
            if event["kind"] == "prompt":
                newest[event["room"]] = event
    found = []
    for room, event in newest.items():
        at = _epoch(event["ts"])
        if event["outcome"] not in RUN_WORDS or at < since or at < last_user.get(room, 0.0):
            continue
        found.append(_item(f"room:{room}", "run", at, at, _topic_title(root, room), RUN_WORDS[event["outcome"]],
                           room, None))
    return found


def _tail(path: Path, since: float):
    try:
        if path.is_symlink() or path.stat().st_mtime < since:
            return
    except OSError:
        return
    for raw in _tail_lines(path):
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            continue
        if isinstance(obj, dict):
            yield obj


def _tail_lines(path: Path) -> list[bytes]:
    try:
        with open(path, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            handle.seek(max(0, size - TAIL_BYTES))
            blob = handle.read(TAIL_BYTES)
    except OSError:
        return []
    lines = blob.split(b"\n")
    return lines[1:] if size > TAIL_BYTES else lines


def _topic_title(root: Path, room: str) -> str:
    from topics import get_topic

    try:
        topic = get_topic(root, room, timeout=0.2)
    except (EventRejected, OSError):
        return room
    title = topic.get("title") if isinstance(topic, dict) else None
    return title if isinstance(title, str) and title else room


def _epoch(stamp: str) -> float:
    return float(timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")))
