"""MAILROOM: every new thought, message or hook question lands here; a local sorter proposes; Daniel files. No Tk.

Sources: ``capture`` (a thought sent to the Mailroom from the capture strip or the phone), ``message`` (a channel
line to Daniel in a room that is no task chat, while he is not talking in that room) and ``hook`` (an agent's
Stop note that ends on a question). The sorter is the quick-capture ranker (``registry.capture``) plus two word
rules: a question drafts a decision, a sentence that starts with a work verb proposes a task chat. No network, no CLI.
Nothing is filed until ``approve``: one card through ``registry.capture`` as Daniel, its task chat, its decision.
``bounce`` sends a letter to Unsorted; a second bounce drops it. ``mailroom.json`` in the data dir keeps it all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

from board.model import valid_chat_room
from events import CHANNEL_DIR_NAME, EventRejected, directory_lock, sanitize_text

STORE_NAME = "mailroom.json"
SOURCES = ("capture", "message", "hook")
KEEP = 200
SEEN_KEEP = 2000
TEXT_LIMIT = 2000
SLACK_S = 5.0
LIVE_S = 600.0
ASKER = "emit:mailroom"
QUESTION_WORDS = frozenset("should shall can could would will do does did is are was which what when where who why how "
                           "may might".split())
WORK_VERBS = frozenset("fix add build make write check review update refactor investigate find test draft plan "
                       "research design port move clean remove rename implement debug ship set wire mend repair "
                       "replace".split())
_ID = re.compile(r"^[0-9a-f]{16}$")
_SENTENCE = re.compile(r"[^.!?\n]*[?]")
_LOOKED: dict[str, tuple] = {}


def valid_id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def load(directory: Path | str) -> dict:
    """The stored state; an empty Mailroom with no cursor when the file is missing or malformed."""
    try:
        data = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        return {"cursor": None, "items": [], "seen": []}
    items = [i for i in data.get("items") or [] if isinstance(i, dict) and valid_id(i.get("id"))]
    seen = [s for s in data.get("seen") or [] if isinstance(s, str)]
    cursor = data.get("cursor")
    return {"cursor": float(cursor) if isinstance(cursor, (int, float)) else None, "items": items, "seen": seen}


def stamp(directory: Path | str) -> tuple:
    try:
        st = (Path(directory) / STORE_NAME).stat()
    except OSError:
        return ()
    return (st.st_mtime_ns, st.st_size)


def asks(text: str) -> str:
    """The first question in ``text`` (a sentence ending in ``?``, or one opening with a question word), else ""."""
    clean = " ".join(str(text).split())
    found = _SENTENCE.search(clean)
    if found:
        return found.group(0).strip()
    words = clean.split(" ", 1)
    return clean if words[0].lower().strip(",:") in QUESTION_WORDS and len(words) > 1 else ""


def propose(index, text: str, room: str = "") -> dict:
    """The sorter: ``topic`` from the capture ranker (the room's topic on a tie), ``chat`` and ``draft``."""
    fallback = room if room in index.titles else ""
    ranked = index.rank(text, fallback)
    firsts = {(s.split() or [""])[0].lower().strip(",:") for s in re.split(r"[.!?\n]+", str(text))}
    return {"topic": ranked[0] if ranked else "", "chat": bool(firsts & WORK_VERBS), "draft": asks(text)[:240]}


def post(directory: Path | str, text: object, sender: str = "user") -> dict | None:
    """A thought into the Mailroom, sorted on arrival; None for empty text."""
    clean = sanitize_text(text, TEXT_LIMIT) if isinstance(text, str) else ""
    if not clean.strip():
        return None
    from registry import capture

    item = _item(uuid.uuid4().hex[:16], "capture", time.time(), clean.strip(), sender, "")
    item.update(propose(capture.build_index(directory), item["text"]))
    with directory_lock(Path(directory)):
        state = load(directory)
        if state["cursor"] is None:
            state["cursor"] = item["ts"]
        state["items"].append(item)
        _save(directory, state)
    return item


def ingest(directory: Path | str, now: float | None = None) -> list[dict]:
    """New channel lines become letters, sorted on arrival; the first run only sets the cursor (no backlog)."""
    root = Path(directory)
    state = load(root)
    at = time.time() if now is None else float(now)
    if state["cursor"] is None:
        with directory_lock(root):
            state = load(root)
            if state["cursor"] is None:
                state["cursor"] = at
                _save(root, state)
        return []
    files = _files(root)
    if _LOOKED.get(str(root)) == (files, state["cursor"]):
        return []
    found = _scan(root, state["cursor"] - SLACK_S, set(state["seen"]))
    _LOOKED[str(root)] = (files, state["cursor"])
    if not found:
        return []
    from registry import capture

    index = capture.build_index(root)
    for item in found:
        item.update(propose(index, item["text"], item["room"]))
    with directory_lock(root):
        state = load(root)
        seen = set(state["seen"])
        fresh = [i for i in found if i["key"] not in seen]
        for item in fresh:
            state["seen"].append(item.pop("key"))
            state["items"].append(item)
        state["seen"] = state["seen"][-SEEN_KEEP:]
        state["cursor"] = max([state["cursor"] or 0.0, *(i["ts"] for i in fresh)])
        state["items"] = state["items"][-KEEP:]
        _save(root, state)
    return fresh


def retopic(directory: Path | str, item_id: object, topic: object) -> bool:
    """Daniel's topic for a letter before he files it; False for an unknown letter or topic."""
    from topics import get_topic, valid_topic_id

    if not valid_id(item_id) or not valid_topic_id(topic) or valid_chat_room(topic):
        return False
    try:
        if get_topic(directory, str(topic), timeout=0.5) is None:
            return False
    except (EventRejected, OSError):
        return False
    return _change(directory, item_id, lambda item: {**item, "topic": topic}) is not None


def bounce(directory: Path | str, item_id: object) -> str | None:
    """A new letter goes to Unsorted; an unsorted one is dropped. The new state, or None for no such letter."""
    if not valid_id(item_id):
        return None
    with directory_lock(Path(directory)):
        state = load(directory)
        item = next((i for i in state["items"] if i["id"] == item_id), None)
        if item is None:
            return None
        if item.get("state") == "unsorted":
            state["items"].remove(item)
            now = "dropped"
        else:
            item["state"] = now = "unsorted"
        _save(directory, state)
    return now


def approve(directory: Path | str, item_id: object, topic: object = None) -> dict | None:
    """File a letter: one card as Daniel, its task chat when proposed, its drafted decision. None: no such letter.

    The letter leaves the store first so a second approve cannot file it twice; a failed filing puts it back.
    """
    from registry import capture

    if not valid_id(item_id):
        return None
    if topic is not None and not retopic(directory, item_id, topic):
        raise EventRejected("missing")
    with directory_lock(Path(directory)):
        state = load(directory)
        item = next((i for i in state["items"] if i["id"] == item_id), None)
        if item is None:
            return None
        state["items"].remove(item)
        _save(directory, state)
    try:
        card, _room = capture.capture(directory, item["text"], item["topic"], False)
        room = _chat(directory, card["id"]) if item.get("chat") else None
        decision = _decide(directory, card, item, room) if item.get("draft") else None
    except BaseException:
        with directory_lock(Path(directory)):
            state = load(directory)
            state["items"].append(item)
            _save(directory, state)
        raise
    return {"card": card, "room": room, "decision": decision, "item": item}


def public(directory: Path | str) -> dict:
    """What the Dungeon and the phone show: new letters, unsorted ones, how many wait on focus. Oldest first.

    While a task is in focus, letters that came after focus began and are not for its topic are held.
    """
    import focus

    state = load(directory)
    held_since = focus.load(directory)
    task, topic, since = held_since["task"], held_since["topic"], held_since["since"]
    titles = _titles(directory)
    shown, unsorted, held = [], [], 0
    for item in sorted(state["items"], key=lambda i: (i["ts"], i["id"])):
        row = {**item, "topic_title": titles.get(item["topic"], item["topic"])}
        if item.get("state") == "unsorted":
            unsorted.append(row)
        elif task and item["ts"] > since and item["topic"] != topic:
            held += 1
        else:
            shown.append(row)
    return {"items": shown, "unsorted": unsorted, "count": len(shown), "held": held}


def counts(directory: Path | str) -> dict:
    """``public`` without titles: ``count``, ``held``, ``unsorted``."""
    import focus

    state, now = load(directory), focus.load(directory)
    count = held = unsorted = 0
    for item in state["items"]:
        if item.get("state") == "unsorted":
            unsorted += 1
        elif now["task"] and item["ts"] > now["since"] and item["topic"] != now["topic"]:
            held += 1
        else:
            count += 1
    return {"count": count, "held": held, "unsorted": unsorted}


def needs_row(directory: Path | str) -> list[dict]:
    """NEEDS-YOU: one ``mail`` row while letters wait (oldest letter, newest change)."""
    items = [i for i in load(directory)["items"] if i.get("state") != "unsorted"]
    if not items:
        return []
    n = len(items)
    return [{"key": "mail:mailroom", "kind": "mail", "ts": min(i["ts"] for i in items),
             "changed": max(i["ts"] for i in items), "title": "Mailroom",
             "detail": f"{n} letter{'s' if n != 1 else ''} to sort", "room": None, "card": None}]


def topics(directory: Path | str) -> list[dict]:
    """Topics a letter can be filed in, by title."""
    return [{"id": k, "title": v} for k, v in sorted(_titles(directory).items(), key=lambda kv: kv[1].lower())]


def _titles(directory: Path | str) -> dict[str, str]:
    from registry import capture

    try:
        return dict(capture.build_index(directory).titles)
    except (EventRejected, OSError):
        return {}


def _item(item_id: str, source: str, ts: float, text: str, sender: str, room: str) -> dict:
    return {"id": item_id, "source": source, "ts": ts, "text": text, "from": sender, "room": room,
            "topic": "", "chat": False, "draft": "", "state": "new"}


def _files(root: Path) -> tuple:
    """Name, size and mtime of every channel log: ``ingest`` reads them again only when this moves."""
    found = []
    try:
        for path in sorted((root / CHANNEL_DIR_NAME).glob("*.jsonl")):
            st = path.stat()
            found.append((path.name, st.st_size, st.st_mtime_ns))
    except OSError:
        return ()
    return tuple(found)


def _scan(root: Path, cutoff: float, seen: set[str]) -> list[dict]:
    """Letters from channel lines newer than ``cutoff`` that were not taken before."""
    from needs_you import _tail_lines

    base = root / CHANNEL_DIR_NAME
    if base.is_symlink() or not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.jsonl")):
        try:
            if path.is_symlink() or path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        last_user = 0.0
        for raw in _tail_lines(path):
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeDecodeError, RecursionError):
                continue
            if not isinstance(obj, dict) or not isinstance(obj.get("ts"), (int, float)):
                continue
            if obj.get("from") == "user":
                last_user = max(last_user, float(obj["ts"]))
                continue
            item = _letter(obj, cutoff, last_user)
            if item is not None and item["key"] not in seen:
                found.append(item)
    return sorted(found, key=lambda i: i["ts"])


def _letter(obj: dict, cutoff: float, last_user: float) -> dict | None:
    ts, room, sender, note, to = float(obj["ts"]), obj.get("channel"), obj.get("from"), obj.get("note"), obj.get("to")
    if ts <= cutoff or not isinstance(room, str) or valid_chat_room(room) or not isinstance(sender, str):
        return None
    if not isinstance(note, str) or not note.strip() or sender.startswith("emit:") or ts - last_user < LIVE_S:
        return None
    kind = obj.get("kind")
    if kind not in (None, "msg"):
        return None
    if to == "user" or (isinstance(to, list) and "user" in to):
        source = "message"
    elif kind is None and to == sender and asks(note):
        source = "hook"
    else:
        return None
    key = obj.get("id") if isinstance(obj.get("id"), str) else f"{room}|{ts!r}|{sender}"
    item = _item(hashlib.sha1(f"{room}|{key}".encode()).hexdigest()[:16], source, ts, note.strip(), sender, room)
    item["key"] = item["id"]
    return item


def _change(directory: Path | str, item_id: str, change) -> dict | None:
    with directory_lock(Path(directory)):
        state = load(directory)
        for at, item in enumerate(state["items"]):
            if item["id"] == item_id:
                state["items"][at] = change(item)
                _save(directory, state)
                return state["items"][at]
    return None


def _chat(directory: Path | str, card_id: str) -> str | None:
    """A Claude task chat on the new card when the runner can launch it; it starts no CLI."""
    from registry.facade import Registry
    from registry.task_chats import cli_ready, start_chat

    if not cli_ready("claude")[0]:
        return None
    _card, chat = start_chat(Registry(directory), card_id, "claude")
    return chat["room"]


def _decide(directory: Path | str, card: dict, item: dict, room: str | None) -> dict:
    """The drafted decision on the card, asked by the agent that wrote the letter (else the Mailroom)."""
    from inbox import valid_agent_id
    from registry import task_decisions
    from registry.facade import Registry

    sender = item.get("from")
    agent = sender if valid_agent_id(sender) and sender != "user" else ASKER
    return task_decisions.ask(Registry(directory), agent, card, item["draft"], room=room,
                              via="hook" if item["source"] == "hook" else "chat")


def _save(directory: Path | str, state: dict) -> None:
    root = Path(directory)
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("mailroom store is a symlink")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)
