"""Per-agent local inbox. No GUI imports — unit tests load this on Linux.

Messages are data. Nothing in ``text`` is executed, imported, or passed to
a process. Sending writes one JSON line per recipient under
``inbox/<agent>.jsonl`` and one channel line so the Chat panel can show it.

A ``:`` cannot appear in a Windows file name, so ``source:id`` is stored as
``source_id``. The JSON record keeps the original id. The cursor file is
``inbox/<agent>.cursor`` and holds the last read message id.

``decision`` and ``decision_answer`` are reserved kinds. Readers accept
them. This module's send path only stores ``msg``. A ``decision_answer``
is written by ``decisions.py`` into the same inbox files.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from chatlog import ALL_ROOMS
from events import (
    CHANNEL_DIR_NAME,
    INBOX_TEXT_LIMIT,
    LOCK_TIMEOUT,
    UUID_RE,
    EventRejected,
    _ACTOR,
    _CHANNEL,
    _restrict_to_user,
    append_channel,
    directory_lock,
    ensure_private_dir,
    sanitize_text,
)
from rooms import build_rooms

INBOX_DIR_NAME = "inbox"
MAX_RECIPIENTS = 64
MAX_LINE_BYTES = 64 * 1024

# Writers emit ``msg`` only. The other two are reserved and documented.
KINDS = frozenset({"msg", "decision", "decision_answer"})
WRITABLE_KIND = "msg"

_BARE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
_DEVICE = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

_MESSAGE_KEYS = (
    "id", "ts", "from", "to", "room", "topic", "kind", "text", "reply_to",
    "decision_id", "choice",
)


@dataclass(frozen=True)
class KnownAgent:
    """One agent the send box can address. ``agent_id`` is the inbox key."""

    agent_id: str
    name: str


class ToPicker:
    """One agent, several agents, or every known agent.

    ``all`` is the rooms registry passed to ``recipients``. Checking an
    agent leaves ``all`` off. An id that is not in that registry is dropped.
    """

    def __init__(self) -> None:
        self.all = True
        self.checked: list[str] = []

    def choose_all(self) -> None:
        self.all = True
        self.checked = []

    def choose(self, agent_ids: Sequence[str]) -> None:
        self.all = False
        self.checked = list(dict.fromkeys(agent_ids))

    def toggle(self, agent_id: str) -> None:
        self.all = False
        if agent_id in self.checked:
            self.checked = [item for item in self.checked if item != agent_id]
        else:
            self.checked.append(agent_id)

    def recipients(self, known: Sequence[KnownAgent]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for agent in known:
            if agent.agent_id in seen:
                continue
            seen.add(agent.agent_id)
            ids.append(agent.agent_id)
        if self.all:
            return ids
        allowed = set(ids)
        return [agent_id for agent_id in self.checked if agent_id in allowed]

    def label(self, known: Sequence[KnownAgent]) -> str:
        if self.all:
            return "All"
        picked = self.recipients(known)
        if not picked:
            return "nobody"
        if len(picked) == 1:
            names = {agent.agent_id: agent.name for agent in known}
            return names.get(picked[0], picked[0])
        return f"{len(picked)} agents"


def valid_agent_id(value: object) -> bool:
    """``user``, ``source:id``, or a bare session id."""
    if not isinstance(value, str) or not value:
        return False
    if value == "user":
        return True
    if _ACTOR.fullmatch(value):
        return True
    return _BARE_ID.fullmatch(value) is not None


def agents_from_registry(agents: object, now: float | None = None) -> list[KnownAgent]:
    """Top-level sessions and their sub rows. Demo rows are skipped."""
    moment = time.time() if now is None else now
    found: list[KnownAgent] = []
    seen: set[str] = set()
    for card in build_rooms(agents, moment):  # type: ignore[arg-type]
        _add_agent(found, seen, card.agent_id, card.name)
        for sub in card.subs:
            _add_agent(found, seen, sub.agent_id, sub.name)
    return found


def _add_agent(found: list[KnownAgent], seen: set[str], agent_id: str, name: str) -> None:
    if agent_id in seen or not valid_agent_id(agent_id):
        return
    seen.add(agent_id)
    label = name.strip() if isinstance(name, str) and name.strip() else agent_id
    found.append(KnownAgent(agent_id, label))


def send_room(choice: object) -> str:
    """Room for a send. The all-rooms filter and a bad label become ``general``."""
    if not isinstance(choice, str) or choice == ALL_ROOMS or not choice.strip():
        return "general"
    if _CHANNEL.fullmatch(choice) or _ACTOR.fullmatch(choice):
        return choice
    return "general"


def inbox_stem(agent_id: str) -> str:
    """File stem for one agent. ``:`` becomes ``_``. Device names are rejected."""
    if not valid_agent_id(agent_id):
        raise EventRejected("schema")
    stem = agent_id.replace(":", "_")
    if (
        not stem
        or stem in {".", ".."}
        or stem.startswith(".")
        or stem.endswith(".")
        or stem.endswith(" ")
        or stem.upper() in _DEVICE
        or any(ch in stem for ch in "\\/<>\"|?*")
    ):
        raise EventRejected("schema")
    return stem


def inbox_root(directory: Path | str) -> Path:
    path = Path(directory) / INBOX_DIR_NAME
    if path.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(path)
    resolved = path.resolve()
    if resolved.name != INBOX_DIR_NAME:
        raise EventRejected("schema")
    return resolved


def _inbox_file(root: Path, agent_id: str, suffix: str) -> Path:
    path = root / (inbox_stem(agent_id) + suffix)
    if path.is_symlink():
        raise EventRejected("schema")
    resolved = path.resolve()
    if resolved.parent != root:
        raise EventRejected("schema")
    return resolved


def _room_pair(obj: dict) -> tuple[str, str]:
    room = obj.get("room", None)
    topic = obj.get("topic", None)
    if room is None and topic is None and obj.get("channel") is not None:
        room = obj.get("channel")
    if room is None and topic is None:
        raise EventRejected("schema")
    if room is None:
        room = topic
    elif topic is not None and topic != room:
        raise EventRejected("schema")
    if not isinstance(room, str):
        raise EventRejected("schema")
    if _CHANNEL.fullmatch(room) is None and _ACTOR.fullmatch(room) is None:
        raise EventRejected("schema")
    return room, room


def validate_message(obj: object, *, write: bool = False) -> dict[str, object]:
    """Return a message dict or raise ``EventRejected``.

    Unknown fields, including ``token``, are dropped. On write only ``msg``
    is accepted. On read the reserved kinds are accepted too. Text is
    sanitised either way. A ``decision_answer`` may also carry
    ``decision_id`` (a UUID) and ``choice`` (one letter, a through f).
    """
    if not isinstance(obj, dict):
        raise EventRejected("schema")
    sender = obj.get("from")
    if not valid_agent_id(sender):
        raise EventRejected("schema")
    raw_to = obj.get("to")
    if isinstance(raw_to, str):
        raw_to = [raw_to]
    if isinstance(raw_to, (str, bytes)) or not isinstance(raw_to, list):
        raise EventRejected("schema")
    if not raw_to or len(raw_to) > MAX_RECIPIENTS:
        raise EventRejected("schema")
    to: list[str] = []
    for item in raw_to:
        if not valid_agent_id(item):
            raise EventRejected("schema")
        if item not in to:
            to.append(item)
    if not to:
        raise EventRejected("schema")
    kind = obj.get("kind", WRITABLE_KIND)
    if not isinstance(kind, str):
        raise EventRejected("schema")
    if write:
        if kind != WRITABLE_KIND:
            raise EventRejected("schema")
    elif kind not in KINDS:
        raise EventRejected("schema")
    text = obj.get("text")
    if not isinstance(text, str):
        raise EventRejected("schema")
    cleaned = sanitize_text(text, INBOX_TEXT_LIMIT)
    if not cleaned:
        raise EventRejected("schema")
    room, topic = _room_pair(obj)
    raw_id = obj.get("id")
    if not isinstance(raw_id, str) or UUID_RE.fullmatch(raw_id) is None:
        raise EventRejected("schema")
    raw_ts = obj.get("ts")
    if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)):
        raise EventRejected("schema")
    try:
        ts = float(raw_ts)
    except (TypeError, ValueError):
        raise EventRejected("schema") from None
    if ts != ts or ts in (float("inf"), float("-inf")):
        raise EventRejected("schema")
    record: dict[str, object] = {
        "id": raw_id.lower(),
        "ts": ts,
        "from": sender,
        "to": to,
        "room": room,
        "topic": topic,
        "kind": kind,
        "text": cleaned,
    }
    if "reply_to" in obj and obj.get("reply_to") is not None:
        reply = obj.get("reply_to")
        if not isinstance(reply, str) or UUID_RE.fullmatch(reply) is None:
            raise EventRejected("schema")
        record["reply_to"] = reply.lower()
    if kind == "decision_answer":
        if "decision_id" in obj and obj.get("decision_id") is not None:
            decision_id = obj.get("decision_id")
            if not isinstance(decision_id, str) or UUID_RE.fullmatch(decision_id) is None:
                raise EventRejected("schema")
            record["decision_id"] = decision_id.lower()
        if "choice" in obj and obj.get("choice") is not None:
            choice = obj.get("choice")
            if not isinstance(choice, str) or len(choice) != 1 or choice not in "abcdef":
                raise EventRejected("schema")
            record["choice"] = choice
    return record


def send_message(
    directory: Path | str,
    *,
    sender: str,
    recipients: Sequence[str],
    text: object,
    room: str | None = None,
    topic: str | None = None,
    kind: str = WRITABLE_KIND,
    reply_to: str | None = None,
    ts: float | None = None,
    message_id: str | None = None,
) -> dict[str, object]:
    """Fan a message out to each recipient inbox and append the channel line.

    ``recipients`` is an explicit list. ``All`` is resolved by the caller.
    A string is not a list of agents. Nothing in ``text`` is executed.
    """
    if isinstance(recipients, (str, bytes)) or not isinstance(recipients, Sequence):
        raise EventRejected("schema")
    record = validate_message({
        "id": message_id or str(uuid.uuid4()),
        "ts": time.time() if ts is None else ts,
        "from": sender,
        "to": list(recipients),
        "room": room if room is not None else (topic if topic is not None else "general"),
        "topic": topic if topic is not None else (room if room is not None else "general"),
        "kind": kind,
        "text": text,
        "reply_to": reply_to,
    }, write=True)
    for agent_id in record["to"]:
        if not isinstance(agent_id, str):
            raise EventRejected("schema")
        inbox_stem(agent_id)
    from topics import ensure_topic
    ensure_topic(directory, str(record["room"]), ts=float(record["ts"]))
    _write_inboxes(directory, record)
    _append_channel_message(directory, record)
    return record


def store_inbox(directory: Path | str, record: dict[str, object]) -> dict[str, object]:
    """Append one readable message to each recipient inbox.

    Reserved kinds are allowed here. ``send_message`` still writes ``msg``
    only. The text is stored. It is not executed.
    """
    checked = validate_message(record, write=False)
    targets = checked["to"]
    if not isinstance(targets, list):
        raise EventRejected("schema")
    for agent_id in targets:
        if not isinstance(agent_id, str):
            raise EventRejected("schema")
        inbox_stem(agent_id)
    _write_inboxes(directory, checked)
    return checked


def post_reply(
    directory: Path | str,
    *,
    agent_id: str,
    message_id: str,
    note: object,
    ts: float | None = None,
    new_id: str | None = None,
) -> dict[str, object]:
    """Append one reply to the channel. The Chat panel is the user's view.

    The reply is not written into an inbox. ``message_id`` must already
    exist in an inbox file or on the channel. The reply's room is the
    parent's room.
    """
    if not valid_agent_id(agent_id) or agent_id == "user":
        raise EventRejected("schema")
    parent = find_message(directory, message_id)
    if parent is None:
        raise EventRejected("missing")
    parent_from = parent["from"]
    if not isinstance(parent_from, str):
        raise EventRejected("schema")
    record = validate_message({
        "id": new_id or str(uuid.uuid4()),
        "ts": time.time() if ts is None else ts,
        "from": agent_id,
        "to": [parent_from],
        "room": parent["room"],
        "topic": parent["room"],
        "kind": WRITABLE_KIND,
        "text": note,
        "reply_to": parent["id"],
    }, write=True)
    from topics import ensure_topic
    ensure_topic(directory, str(record["room"]), ts=float(record["ts"]))
    _append_channel_message(directory, record)
    return record


def find_message(directory: Path | str, message_id: str) -> dict[str, object] | None:
    """A stored message with this id, from an inbox file or the channel."""
    if not isinstance(message_id, str) or UUID_RE.fullmatch(message_id) is None:
        raise EventRejected("schema")
    wanted = message_id.lower()
    base = Path(directory)
    for folder, adapt in (
        (INBOX_DIR_NAME, False),
        (CHANNEL_DIR_NAME, True),
    ):
        root = base / folder
        if root.is_symlink() or not root.is_dir():
            continue
        try:
            paths = sorted(root.glob("*.jsonl"))
        except OSError:
            continue
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.resolve().parent != root.resolve():
                    continue
            except OSError:
                continue
            for obj in _iter_objects(path):
                if str(obj.get("id", "")).lower() != wanted:
                    continue
                try:
                    if adapt:
                        return _message_from_channel(obj)
                    return validate_message(obj, write=False)
                except EventRejected:
                    continue
    return None


def read_unread(
    directory: Path | str,
    agent_id: str,
    since: str | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict[str, object]]:
    """Messages after the cursor, or after ``since`` when that id is passed.

    The cursor becomes the last returned id when that id is at or after the
    previous cursor. An empty read leaves the cursor where it is. A cursor
    id that is no longer in the file does not hide the rows that remain.
    ``since`` must be an id in the file. A missing inbox is an empty read.
    """
    if not valid_agent_id(agent_id):
        raise EventRejected("schema")
    if since is not None:
        if not isinstance(since, str) or UUID_RE.fullmatch(since) is None:
            raise EventRejected("schema")
        since = since.lower()
    base = Path(directory)
    root_path = base / INBOX_DIR_NAME
    if root_path.is_symlink():
        raise EventRejected("schema")
    if not root_path.is_dir():
        if since is not None:
            raise EventRejected("missing")
        return []
    root = root_path.resolve()
    with directory_lock(root, timeout=timeout):
        path = _inbox_file(root, agent_id, ".jsonl")
        messages = _load_messages(path, agent_id)
        cursor_path = _inbox_file(root, agent_id, ".cursor")
        cursor = _read_cursor(cursor_path)
        window = _after(messages, since if since is not None else cursor, required=since is not None)
        if window:
            last = str(window[-1]["id"])
            if _pos(messages, last) >= _pos(messages, cursor):
                _write_cursor(cursor_path, last)
        return window


def format_messages(entries: Sequence[dict[str, object]], *, as_json: bool = False) -> str:
    """Plain text or one JSON array. Either way the rows are untrusted data."""
    if as_json:
        payload = [{key: entry[key] for key in _MESSAGE_KEYS if key in entry} for entry in entries]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    lines = ["untrusted data from the sender"]
    if not entries:
        lines.append("(no entries)")
    for entry in entries:
        to = entry.get("to")
        targets = ",".join(to) if isinstance(to, list) else ""
        reply = entry.get("reply_to") or ""
        extra = ""
        if entry.get("decision_id"):
            extra += f" decision_id={entry['decision_id']}"
        if entry.get("choice"):
            extra += f" choice={entry['choice']}"
        lines.append(
            "id={id} from={sender} to={to} room={room} kind={kind} reply_to={reply}{extra} text={text}".format(
                id=entry.get("id", ""),
                sender=entry.get("from", ""),
                to=targets,
                room=entry.get("room", ""),
                kind=entry.get("kind", ""),
                reply=reply,
                extra=extra,
                text=entry.get("text", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _write_inboxes(directory: Path | str, record: dict[str, object]) -> None:
    recipients = record["to"]
    if not isinstance(recipients, list):
        raise EventRejected("schema")
    root = inbox_root(directory)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with directory_lock(root):
        for agent_id in recipients:
            if not isinstance(agent_id, str):
                raise EventRejected("schema")
            path = _inbox_file(root, agent_id, ".jsonl")
            if path.is_symlink():
                raise EventRejected("schema")
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
            _restrict_to_user(path)


def _append_channel_message(directory: Path | str, record: dict[str, object]) -> None:
    sender = record["from"]
    name = "You" if sender == "user" else str(sender)
    entry: dict[str, object] = {
        "ts": record["ts"],
        "from": sender,
        "to": record["to"],
        "channel": record["room"],
        "icon": "speech",
        "note": record["text"],
        "name": name,
        "id": record["id"],
        "kind": "msg",
    }
    if record.get("reply_to"):
        entry["reply_to"] = record["reply_to"]
    append_channel(Path(directory), entry, note_limit=INBOX_TEXT_LIMIT)


def _message_from_channel(obj: dict) -> dict[str, object]:
    if obj.get("kind") in KINDS and isinstance(obj.get("text"), str):
        return validate_message(obj, write=False)
    text = obj.get("text") if isinstance(obj.get("text"), str) else obj.get("note")
    adapted: dict[str, object] = {
        "id": obj.get("id"),
        "ts": obj.get("ts"),
        "from": obj.get("from"),
        "to": obj.get("to"),
        "room": obj.get("room") or obj.get("channel") or obj.get("topic"),
        "topic": obj.get("topic") or obj.get("room") or obj.get("channel"),
        "kind": obj.get("kind") or WRITABLE_KIND,
        "text": text if isinstance(text, str) else "",
    }
    if obj.get("reply_to") is not None:
        adapted["reply_to"] = obj.get("reply_to")
    return validate_message(adapted, write=False)


def _load_messages(path: Path, agent_id: str) -> list[dict[str, object]]:
    if not path.is_file() or path.is_symlink():
        return []
    found: list[dict[str, object]] = []
    for obj in _iter_objects(path):
        try:
            message = validate_message(obj, write=False)
        except EventRejected:
            continue
        targets = message.get("to")
        if not isinstance(targets, list) or agent_id not in targets:
            continue
        found.append(message)
    return found


def _iter_objects(path: Path):
    try:
        blob = path.read_bytes()
    except OSError:
        return
    if len(blob) > 8 * 1024 * 1024:
        blob = blob[: 8 * 1024 * 1024]
    for raw in _split_lines(blob):
        if not raw.strip() or len(raw) > MAX_LINE_BYTES:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _split_lines(blob: bytes):
    """Yield complete lines. A trailing partial line is ignored. CRLF is one break."""
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    start = 0
    for index, byte in enumerate(blob):
        if byte != 0x0A:
            continue
        raw = blob[start:index]
        start = index + 1
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        yield raw


def _after(messages: list[dict[str, object]], start_id: str | None, *, required: bool):
    if not start_id:
        return list(messages)
    for index, message in enumerate(messages):
        if message["id"] == start_id:
            return messages[index + 1:]
    if required:
        raise EventRejected("missing")
    return list(messages)


def _pos(messages: list[dict[str, object]], message_id: str | None) -> int:
    if not message_id:
        return -1
    for index, message in enumerate(messages):
        if message["id"] == message_id:
            return index
    return -1


def _read_cursor(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    text = blob.decode("utf-8", errors="replace").strip().strip("\r")
    if UUID_RE.fullmatch(text) is None:
        return None
    return text.lower()


def _write_cursor(path: Path, message_id: str) -> None:
    if path.is_symlink():
        raise EventRejected("schema")
    tmp = path.with_name(path.name + ".tmp")
    if tmp.is_symlink():
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (message_id + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)
