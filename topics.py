"""Topic memory for local chat. No GUI imports on the store path.

A topic is the room id already stored on channel, inbox, and decision
records. Unknown rooms become an open topic. The app stores, shows, and
notifies. It does not execute text and it does not call a model.

Files live under the per-user data directory at ``topics/<id>.json``.
The directory is owner-only. Writes take ``directory_lock`` (a timeout,
and the handle is closed before the lock returns). ``project`` is a
folder name. An absolute path is rejected and is never stored.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Iterable, Sequence

from events import (
    CHANNEL_DIR_NAME,
    LOCK_TIMEOUT,
    UUID_RE,
    EventRejected,
    _ACTOR,
    _CHANNEL,
    _restrict_to_user,
    directory_lock,
    ensure_private_dir,
    sanitize_text,
)

TOPICS_DIR_NAME = "topics"
SUMMARY_LIMIT = 1500
PIN_LIMIT = 240
TITLE_LIMIT = 80
PROJECT_LIMIT = 80
BRANCH_LIMIT = 128
MAX_PINS = 30
MAX_MEMBERS = 64
VISIBLE_MESSAGES = 200
SUMMARY_STALE = 50
DEFAULT_SHOW = 10
MAX_SHOW = VISIBLE_MESSAGES
MAX_LINE_BYTES = 64 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024

STATUSES = frozenset({"open", "waiting_on_user", "done"})
PIN_KINDS = frozenset({"fact", "decision"})
STATUS_ORDER = {"open": 0, "waiting_on_user": 1, "done": 2}
STATUS_LABEL = {
    "open": "open",
    "waiting_on_user": "waiting on you",
    "done": "done",
}
STATUS_COLOR = {
    "open": "#4488ff",
    "waiting_on_user": "#ffcf4a",
    "done": "#9a98b8",
}

_DEVICE = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})
_BARE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")

_TOPIC_KEYS = (
    "id", "title", "project", "branch", "status", "members", "summary",
    "summary_count", "pinned", "created", "updated",
)
_PIN_KEYS = ("id", "ts", "author", "kind", "text")
_SHOW_KEYS = ("id", "summary", "pinned", "messages", "needs_summary")
_MESSAGE_KEYS = ("ts", "from", "text", "icon")


def valid_topic_id(value: object) -> bool:
    """A room slug. The same strings the channel already accepts."""
    if not isinstance(value, str) or not value:
        return False
    if _CHANNEL.fullmatch(value) is None and _ACTOR.fullmatch(value) is None:
        return False
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    if (
        not stem
        or stem in {".", ".."}
        or stem.startswith(".")
        or stem.endswith(".")
        or stem.endswith(" ")
        or stem.upper() in _DEVICE
    ):
        return False
    return True


def valid_member(value: object) -> bool:
    """An agent id. ``user`` is an author, not a member."""
    if not isinstance(value, str) or not value or value == "user":
        return False
    if _ACTOR.fullmatch(value) is None and _BARE_ID.fullmatch(value) is None:
        return False
    stem = value.replace(":", "_")
    if stem.upper() in _DEVICE or stem in {".", ".."}:
        return False
    return True


def clean_project(value: object) -> str:
    """A folder name. A path, a drive, or ``~`` is rejected.

    The empty string clears the project. The returned value never contains
    a separator, so it cannot be an absolute path.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EventRejected("schema")
    raw = value.strip()
    if not raw:
        return ""
    if raw.startswith(("/", "\\", "~")) or "\\" in raw or "/" in raw or ":" in raw:
        raise EventRejected("schema")
    if raw in {".", ".."} or raw.endswith(".") or raw.endswith(" "):
        raise EventRejected("schema")
    cleaned = sanitize_text(raw, PROJECT_LIMIT)
    if not cleaned or cleaned.startswith(("~", "/", "\\")):
        raise EventRejected("schema")
    if "\\" in cleaned or "/" in cleaned or ":" in cleaned:
        raise EventRejected("schema")
    if cleaned in {".", ".."}:
        raise EventRejected("schema")
    return cleaned


def clean_branch(value: object) -> str:
    """Optional git branch. A filesystem path is rejected. ``feat/name`` stays."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EventRejected("schema")
    raw = value.strip()
    if not raw:
        return ""
    if raw.startswith(("/", "\\", "~")) or "\\" in raw or ":" in raw:
        raise EventRejected("schema")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise EventRejected("schema")
    cleaned = sanitize_text(raw, BRANCH_LIMIT)
    if not cleaned or cleaned.startswith(("/", "\\", "~")) or "\\" in cleaned or ":" in cleaned:
        raise EventRejected("schema")
    if any(part in {"", ".", ".."} for part in cleaned.split("/")):
        raise EventRejected("schema")
    return cleaned


def clean_title(value: object) -> str:
    text = sanitize_text(value, TITLE_LIMIT)
    if not text:
        raise EventRejected("schema")
    return text


def status_label(status: object) -> str:
    if not isinstance(status, str):
        return "open"
    return STATUS_LABEL.get(status, "open")


def latest_per_topic(lines: Sequence[object], limit: int = VISIBLE_MESSAGES) -> list:
    """Keep the newest ``limit`` lines of each room. Older lines stay on disk.

    ``lines`` is in time order. The kept lines stay in that order. Objects
    expose ``room``. The input sequence is not modified.
    """
    cap = max(0, int(limit))
    counts: dict[str, int] = {}
    keep: list[bool] = [False] * len(lines)
    for index in range(len(lines) - 1, -1, -1):
        room = getattr(lines[index], "room", "")
        seen = counts.get(room, 0)
        if seen >= cap:
            continue
        counts[room] = seen + 1
        keep[index] = True
    return [line for line, kept in zip(lines, keep) if kept]


def group_by_project(topics: Sequence[dict]) -> list[tuple[str, list[dict]]]:
    """``(project, topics)`` with the empty project last. Open topics come first."""
    buckets: dict[str, list[dict]] = {}
    for topic in topics:
        project = topic.get("project") if isinstance(topic.get("project"), str) else ""
        buckets.setdefault(project or "", []).append(topic)

    def topic_key(topic: dict) -> tuple:
        status = str(topic.get("status") or "")
        title = str(topic.get("title") or "")
        return (STATUS_ORDER.get(status, 9), title.casefold(), str(topic.get("id") or ""))

    grouped: list[tuple[str, list[dict]]] = []
    names = sorted(buckets, key=lambda name: (name == "", name.casefold()))
    for name in names:
        grouped.append((name, sorted(buckets[name], key=topic_key)))
    return grouped


def source_stamp(directory: Path | str) -> tuple:
    """Sizes and mtimes of the logs that can introduce a room. Not a path list."""
    root = Path(directory)
    found: list[tuple[str, int, int]] = []
    for folder in (CHANNEL_DIR_NAME, "inbox"):
        base = root / folder
        if base.is_symlink() or not base.is_dir():
            continue
        try:
            paths = sorted(base.glob("*.jsonl"))
        except OSError:
            continue
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            found.append((f"{folder}/{path.name}", int(st.st_mtime_ns), int(st.st_size)))
    decisions = root / "decisions.jsonl"
    if decisions.is_file() and not decisions.is_symlink():
        try:
            st = decisions.stat()
            found.append(("decisions.jsonl", int(st.st_mtime_ns), int(st.st_size)))
        except OSError:
            pass
    return tuple(found)


def discover_room_ids(directory: Path | str) -> list[str]:
    """Room ids already stored on channel, inbox, and decision lines.

    The files are not modified. A bad line is skipped. Ids come from the
    record, not from a directory listing of the host.
    """
    root = Path(directory)
    found: list[str] = []
    seen: set[str] = set()

    def take(value: object) -> None:
        if isinstance(value, str) and value not in seen and valid_topic_id(value):
            seen.add(value)
            found.append(value)

    for folder in (CHANNEL_DIR_NAME, "inbox"):
        base = root / folder
        if base.is_symlink() or not base.is_dir():
            continue
        try:
            paths = sorted(base.glob("*.jsonl"))
        except OSError:
            continue
        for path in paths:
            for obj in _iter_json_objects(path):
                take(obj.get("channel"))
                take(obj.get("room"))
                take(obj.get("topic"))
    decisions = root / "decisions.jsonl"
    if decisions.is_file() and not decisions.is_symlink():
        for obj in _iter_json_objects(decisions):
            take(obj.get("room"))
            take(obj.get("topic"))
    return found


def topic_messages(directory: Path | str, topic_id: str) -> list[dict[str, object]]:
    """Channel lines for one room, oldest first. The jsonl is not modified.

    Inbox copies are not counted again. Each message is ``ts``, ``from``,
    ``text``, and ``icon``. Text is the note already stored, capped at 240
    by the channel reader.
    """
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    from chatlog import parse_record

    root = Path(directory) / CHANNEL_DIR_NAME
    if root.is_symlink() or not root.is_dir():
        return []
    found: list[dict[str, object]] = []
    try:
        paths = sorted(root.glob("*.jsonl"))
    except OSError:
        return []
    for path in paths:
        for obj in _iter_json_objects(path):
            room = obj.get("channel") or obj.get("room") or obj.get("topic")
            if room != topic_id:
                continue
            line = parse_record(obj, localtime=time.gmtime)
            if line is None or line.room != topic_id:
                continue
            found.append({
                "ts": line.ts,
                "from": line.sender,
                "text": line.note,
                "icon": line.icon,
            })
    found.sort(key=lambda item: float(item["ts"]))
    return found


def ensure_topic(
    directory: Path | str,
    topic_id: str,
    *,
    title: str | None = None,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Return the topic, creating an open one when the id is new.

    An existing topic is returned unchanged, including its status.
    """
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    moment = _finite(time.time() if ts is None else ts)
    heading = clean_title(title) if title is not None else _default_title(topic_id)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id)
        if current is not None:
            return current
        record = _blank(topic_id, moment, heading)
        _write_one(root, record)
        return record


def sync_topics(directory: Path | str, timeout: float = LOCK_TIMEOUT) -> list[dict[str, object]]:
    """Create an open topic for every room already on disk. Logs stay as they are."""
    for topic_id in discover_room_ids(directory):
        ensure_topic(directory, topic_id, timeout=timeout)
    return list_topics(directory, timeout=timeout)


def list_topics(
    directory: Path | str,
    *,
    statuses: Sequence[str] | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict[str, object]]:
    """Stored topics, grouped order (project, then status, then title)."""
    allowed = _status_filter(statuses)
    root = _existing_root(directory)
    if root is None:
        return []
    with directory_lock(root, timeout=timeout):
        rows = _read_all(root)
    if allowed is not None:
        rows = [row for row in rows if row.get("status") in allowed]
    flat: list[dict[str, object]] = []
    for _project, group in group_by_project(rows):
        flat.extend(group)
    return flat


def get_topic(
    directory: Path | str,
    topic_id: str,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object] | None:
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    root = _existing_root(directory)
    if root is None:
        return None
    with directory_lock(root, timeout=timeout):
        return _read_one(root, topic_id)


def show_topic(
    directory: Path | str,
    topic_id: str,
    *,
    last: int = DEFAULT_SHOW,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Summary, pins, and the last ``last`` messages. Nothing else.

    ``needs_summary`` is true when more than 50 messages arrived after the
    summary was last replaced. The channel file is left untouched.
    """
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    window = _show_window(last)
    topic = get_topic(directory, topic_id, timeout=timeout)
    if topic is None:
        if topic_id not in discover_room_ids(directory):
            raise EventRejected("missing")
        topic = ensure_topic(directory, topic_id, timeout=timeout)
    messages = topic_messages(directory, topic_id)
    baseline = int(topic.get("summary_count") or 0)
    return {
        "id": topic["id"],
        "summary": topic.get("summary") or "",
        "pinned": [dict(item) for item in topic.get("pinned") or []],  # type: ignore[union-attr]
        "messages": messages[-window:],
        "needs_summary": (len(messages) - baseline) > SUMMARY_STALE,
    }


def set_topic(
    directory: Path | str,
    topic_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    branch: str | None = None,
    project: str | None = None,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Replace the fields that were passed. Other fields stay."""
    if title is None and status is None and branch is None and project is None:
        raise EventRejected("schema")
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    new_title = clean_title(title) if title is not None else None
    new_status = _clean_status(status) if status is not None else None
    new_branch = clean_branch(branch) if branch is not None else None
    new_project = clean_project(project) if project is not None else None
    moment = _finite(time.time() if ts is None else ts)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id) or _blank(topic_id, moment, new_title or _default_title(topic_id))
        if new_title is not None:
            current["title"] = new_title
        if new_status is not None:
            current["status"] = new_status
        if new_branch is not None:
            current["branch"] = new_branch
        if new_project is not None:
            current["project"] = new_project
        current["updated"] = moment
        _write_one(root, current)
        return current


def set_summary(
    directory: Path | str,
    topic_id: str,
    note: object,
    *,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Replace the summary. The message count at this moment is remembered."""
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    text = sanitize_text(note, SUMMARY_LIMIT)
    if not text:
        raise EventRejected("schema")
    moment = _finite(time.time() if ts is None else ts)
    count = len(topic_messages(directory, topic_id))
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id) or _blank(topic_id, moment, _default_title(topic_id))
        current["summary"] = text
        current["summary_count"] = count
        current["updated"] = moment
        _write_one(root, current)
        return current


def pin_item(
    directory: Path | str,
    topic_id: str,
    *,
    kind: str,
    text: object,
    author: str = "user",
    ts: float | None = None,
    pin_id: str | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Append one fact or decision. The same kind and text is kept once.

    At most 30 pins. Each text is capped at 240 characters. The 31st pin
    writes nothing.
    """
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    if kind not in PIN_KINDS:
        raise EventRejected("schema")
    cleaned = sanitize_text(text, PIN_LIMIT)
    if not cleaned:
        raise EventRejected("schema")
    if author != "user" and not valid_member(author):
        raise EventRejected("schema")
    if pin_id is None:
        ident = str(uuid.uuid4())
    elif isinstance(pin_id, str) and UUID_RE.fullmatch(pin_id):
        ident = pin_id.lower()
    else:
        raise EventRejected("schema")
    moment = _finite(time.time() if ts is None else ts)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id) or _blank(topic_id, moment, _default_title(topic_id))
        pins = [dict(item) for item in current.get("pinned") or []]  # type: ignore[union-attr]
        for item in pins:
            if item.get("kind") == kind and item.get("text") == cleaned:
                return current
        if len(pins) >= MAX_PINS:
            raise EventRejected("limit")
        pins.append({
            "id": ident,
            "ts": moment,
            "author": author,
            "kind": kind,
            "text": cleaned,
        })
        current["pinned"] = pins
        current["updated"] = moment
        _write_one(root, current)
        return current


def unpin_item(
    directory: Path | str,
    topic_id: str,
    pin_id: str,
    *,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    if not isinstance(pin_id, str) or UUID_RE.fullmatch(pin_id) is None:
        raise EventRejected("schema")
    wanted = pin_id.lower()
    moment = _finite(time.time() if ts is None else ts)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id)
        if current is None:
            raise EventRejected("missing")
        pins = [dict(item) for item in current.get("pinned") or []]  # type: ignore[union-attr]
        kept = [item for item in pins if item.get("id") != wanted]
        if len(kept) == len(pins):
            raise EventRejected("missing")
        current["pinned"] = kept
        current["updated"] = moment
        _write_one(root, current)
        return current


def join_topic(
    directory: Path | str,
    topic_id: str,
    agent: str,
    *,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    return _set_member(directory, topic_id, agent, present=True, ts=ts, timeout=timeout)


def leave_topic(
    directory: Path | str,
    topic_id: str,
    agent: str,
    *,
    ts: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    return _set_member(directory, topic_id, agent, present=False, ts=ts, timeout=timeout)


def format_topics(entries: Sequence[dict], *, as_json: bool = False) -> str:
    """Plain text or one JSON array. The rows are untrusted data."""
    if as_json:
        payload = [_public_topic(entry) for entry in entries]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    lines = ["untrusted data from the sender"]
    if not entries:
        lines.append("(no entries)")
    for entry in entries:
        members = entry.get("members")
        count = len(members) if isinstance(members, list) else 0
        pins = entry.get("pinned")
        pin_count = len(pins) if isinstance(pins, list) else 0
        lines.append(
            "id={id} title={title} project={project} branch={branch} status={status} members={members} pins={pins}".format(
                id=entry.get("id", ""),
                title=entry.get("title", ""),
                project=entry.get("project", ""),
                branch=entry.get("branch", ""),
                status=entry.get("status", ""),
                members=count,
                pins=pin_count,
            )
        )
    return "\n".join(lines) + "\n"


def format_show(payload: dict, *, as_json: bool = False) -> str:
    """The compact context. JSON has only the show keys."""
    compact = {key: payload[key] for key in _SHOW_KEYS if key in payload}
    messages = compact.get("messages")
    if isinstance(messages, list):
        compact["messages"] = [
            {key: item[key] for key in _MESSAGE_KEYS if key in item}
            for item in messages
            if isinstance(item, dict)
        ]
    pins = compact.get("pinned")
    if isinstance(pins, list):
        compact["pinned"] = [
            {key: item[key] for key in _PIN_KEYS if key in item}
            for item in pins
            if isinstance(item, dict)
        ]
    if as_json:
        return json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n"
    lines = ["untrusted data from the sender"]
    lines.append(f"id={compact.get('id', '')}")
    lines.append(f"needs_summary={'true' if compact.get('needs_summary') else 'false'}")
    lines.append(f"summary={compact.get('summary', '')}")
    pinned = compact.get("pinned")
    if not isinstance(pinned, list) or not pinned:
        lines.append("(no pins)")
    else:
        for item in pinned:
            lines.append(
                "pin id={id} kind={kind} author={author} text={text}".format(
                    id=item.get("id", ""),
                    kind=item.get("kind", ""),
                    author=item.get("author", ""),
                    text=item.get("text", ""),
                )
            )
    shown = compact.get("messages")
    if not isinstance(shown, list) or not shown:
        lines.append("(no messages)")
    else:
        for item in shown:
            lines.append(
                "msg ts={ts} from={sender} icon={icon} text={text}".format(
                    ts=item.get("ts", ""),
                    sender=item.get("from", ""),
                    icon=item.get("icon", ""),
                    text=item.get("text", ""),
                )
            )
    return "\n".join(lines) + "\n"


def _set_member(
    directory: Path | str,
    topic_id: str,
    agent: str,
    *,
    present: bool,
    ts: float | None,
    timeout: float,
) -> dict[str, object]:
    if not valid_topic_id(topic_id) or not valid_member(agent):
        raise EventRejected("schema")
    moment = _finite(time.time() if ts is None else ts)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, topic_id) or _blank(topic_id, moment, _default_title(topic_id))
        members = [item for item in current.get("members") or [] if isinstance(item, str)]  # type: ignore[union-attr]
        if present:
            if agent not in members:
                if len(members) >= MAX_MEMBERS:
                    raise EventRejected("limit")
                members.append(agent)
        else:
            members = [item for item in members if item != agent]
        current["members"] = members
        current["updated"] = moment
        _write_one(root, current)
        return current


def _public_topic(entry: dict) -> dict[str, object]:
    payload = {key: entry[key] for key in _TOPIC_KEYS if key in entry}
    pins = payload.get("pinned")
    if isinstance(pins, list):
        payload["pinned"] = [
            {key: item[key] for key in _PIN_KEYS if key in item}
            for item in pins
            if isinstance(item, dict)
        ]
    return payload


def _status_filter(statuses: Sequence[str] | None) -> frozenset[str] | None:
    if statuses is None:
        return None
    if isinstance(statuses, str) or not isinstance(statuses, Sequence):
        raise EventRejected("schema")
    allowed: list[str] = []
    for item in statuses:
        if item not in STATUSES:
            raise EventRejected("schema")
        if item not in allowed:
            allowed.append(item)
    return frozenset(allowed)


def _show_window(last: object) -> int:
    if isinstance(last, bool) or not isinstance(last, int):
        raise EventRejected("schema")
    if not 1 <= last <= MAX_SHOW:
        raise EventRejected("schema")
    return last


def _clean_status(status: object) -> str:
    if not isinstance(status, str) or status not in STATUSES:
        raise EventRejected("schema")
    return status


def _default_title(topic_id: str) -> str:
    title = sanitize_text(topic_id, TITLE_LIMIT)
    return title or topic_id[:TITLE_LIMIT]


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventRejected("schema")
    try:
        ts = float(value)
    except (TypeError, ValueError):
        raise EventRejected("schema") from None
    if ts != ts or ts in (float("inf"), float("-inf")):
        raise EventRejected("schema")
    return ts


def _blank(topic_id: str, ts: float, title: str) -> dict[str, object]:
    return {
        "id": topic_id,
        "title": title,
        "project": "",
        "branch": "",
        "status": "open",
        "members": [],
        "summary": "",
        "summary_count": 0,
        "pinned": [],
        "created": ts,
        "updated": ts,
    }


def _validate_pin(obj: object) -> dict[str, object]:
    if not isinstance(obj, dict):
        raise EventRejected("schema")
    raw_id = obj.get("id")
    if not isinstance(raw_id, str) or UUID_RE.fullmatch(raw_id) is None:
        raise EventRejected("schema")
    kind = obj.get("kind")
    if kind not in PIN_KINDS:
        raise EventRejected("schema")
    author = obj.get("author")
    if author != "user" and not valid_member(author):
        raise EventRejected("schema")
    text = sanitize_text(obj.get("text"), PIN_LIMIT)
    if not text:
        raise EventRejected("schema")
    return {
        "id": raw_id.lower(),
        "ts": _finite(obj.get("ts")),
        "author": str(author),
        "kind": str(kind),
        "text": text,
    }


def _validate_topic(obj: object) -> tuple[dict[str, object], bool]:
    """Return the topic and whether a path or an over-long field was repaired."""
    if not isinstance(obj, dict):
        raise EventRejected("schema")
    topic_id = obj.get("id")
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    status = obj.get("status")
    if status not in STATUSES:
        raise EventRejected("schema")
    title = sanitize_text(obj.get("title"), TITLE_LIMIT) or _default_title(str(topic_id))
    raw_project = obj.get("project", "")
    repaired = False
    try:
        project = clean_project(raw_project if raw_project is not None else "")
    except EventRejected:
        project = ""
        repaired = True
    if isinstance(raw_project, str) and raw_project not in {project, ""} and project == "":
        repaired = True
    raw_branch = obj.get("branch", "")
    try:
        branch = clean_branch(raw_branch if raw_branch is not None else "")
    except EventRejected:
        branch = ""
        repaired = True
    summary_raw = obj.get("summary") if isinstance(obj.get("summary"), str) else ""
    summary = sanitize_text(summary_raw, SUMMARY_LIMIT)
    if summary != summary_raw.strip()[:SUMMARY_LIMIT] and len(summary_raw) > SUMMARY_LIMIT:
        repaired = True
    if summary_raw and summary != sanitize_text(summary_raw, max(len(summary_raw), 1)):
        repaired = True
    members: list[str] = []
    raw_members = obj.get("members")
    if isinstance(raw_members, list):
        for item in raw_members:
            if valid_member(item) and item not in members:
                members.append(str(item))
        if len(members) > MAX_MEMBERS:
            members = members[:MAX_MEMBERS]
            repaired = True
    pins: list[dict[str, object]] = []
    raw_pins = obj.get("pinned")
    if isinstance(raw_pins, list):
        for item in raw_pins:
            try:
                pin = _validate_pin(item)
            except EventRejected:
                repaired = True
                continue
            if any(existing.get("id") == pin["id"] for existing in pins):
                repaired = True
                continue
            raw_text = item.get("text") if isinstance(item, dict) else ""
            if isinstance(raw_text, str) and len(raw_text) > PIN_LIMIT:
                repaired = True
            pins.append(pin)
        if len(pins) > MAX_PINS:
            pins = pins[:MAX_PINS]
            repaired = True
    try:
        count = int(obj.get("summary_count") or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        count = 0
        repaired = True
    if count < 0:
        count = 0
        repaired = True
    record = {
        "id": str(topic_id),
        "title": title,
        "project": project,
        "branch": branch,
        "status": str(status),
        "members": members,
        "summary": summary,
        "summary_count": count,
        "pinned": pins,
        "created": _finite(obj.get("created", obj.get("updated", 0))),
        "updated": _finite(obj.get("updated", obj.get("created", 0))),
    }
    return record, repaired


def _prepare_root(directory: Path | str) -> Path:
    base = Path(directory)
    if base.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(base)
    root = base / TOPICS_DIR_NAME
    if root.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(root)
    resolved = root.resolve()
    if resolved.name != TOPICS_DIR_NAME:
        raise EventRejected("schema")
    return resolved


def _existing_root(directory: Path | str) -> Path | None:
    base = Path(directory)
    if base.is_symlink() or not base.is_dir():
        return None
    root = base / TOPICS_DIR_NAME
    if root.is_symlink() or not root.is_dir():
        return None
    try:
        resolved = root.resolve()
    except OSError:
        raise EventRejected("schema") from None
    if resolved.name != TOPICS_DIR_NAME:
        raise EventRejected("schema")
    return resolved


def _file_name(topic_id: str) -> str:
    if not valid_topic_id(topic_id):
        raise EventRejected("schema")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", topic_id)[:80]
    return stem + ".json"


def _topic_path(root: Path, topic_id: str) -> Path:
    path = root / _file_name(topic_id)
    if path.is_symlink():
        raise EventRejected("schema")
    if path.exists():
        resolved = path.resolve()
        if resolved.parent != root:
            raise EventRejected("schema")
        return resolved
    if path.parent.resolve() != root:
        raise EventRejected("schema")
    return path


def _read_one(root: Path, topic_id: str) -> dict[str, object] | None:
    path = _topic_path(root, topic_id)
    if not path.is_file() or path.is_symlink():
        return None
    record, repaired = _load_path(path)
    if record is None:
        return None
    if record.get("id") != topic_id:
        raise EventRejected("schema")
    if repaired:
        _write_one(root, record)
    return record


def _read_all(root: Path) -> list[dict[str, object]]:
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return []
    found: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        if path.name.endswith(".tmp") or path.is_symlink() or not path.is_file():
            continue
        try:
            if path.resolve().parent != root:
                continue
        except OSError:
            continue
        record, repaired = _load_path(path)
        if record is None:
            continue
        ident = str(record["id"])
        if ident in seen:
            continue
        seen.add(ident)
        if repaired:
            _write_one(root, record)
        found.append(record)
    return found


def _load_path(path: Path) -> tuple[dict[str, object] | None, bool]:
    try:
        blob = path.read_bytes()
    except OSError:
        return None, False
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    if len(blob) > MAX_FILE_BYTES:
        blob = blob[:MAX_FILE_BYTES]
    text = blob.decode("utf-8", errors="replace").strip("\r\n")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, False
    try:
        return _validate_topic(obj)
    except EventRejected:
        return None, False


def _write_one(root: Path, record: dict[str, object]) -> None:
    path = _topic_path(root, str(record["id"]))
    if path.is_symlink():
        raise EventRejected("schema")
    payload = json.dumps(_public_topic(record), ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    if tmp.is_symlink() or tmp.resolve().parent != root and tmp.parent.resolve() != root:
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)


def _iter_json_objects(path: Path) -> Iterable[dict]:
    if path.is_symlink() or not path.is_file():
        return
    try:
        if path.resolve().parent != path.parent.resolve():
            return
    except OSError:
        return
    try:
        blob = path.read_bytes()
    except OSError:
        return
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    if len(blob) > MAX_FILE_BYTES:
        blob = blob[:MAX_FILE_BYTES]
    start = 0
    for index, byte in enumerate(blob):
        if byte != 0x0A:
            continue
        raw = blob[start:index]
        start = index + 1
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        obj = _parse_line(raw)
        if obj is not None:
            yield obj


def _parse_line(raw: bytes) -> dict | None:
    if not raw.strip() or len(raw) > MAX_LINE_BYTES:
        return None
    try:
        text = raw.decode("utf-8")
        obj = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(obj, dict):
        return obj
    return None


def write_topics_preview(path: Path | str | None = None) -> Path:
    """Draw the topics list and a chat header from simulated rows.

    The picture does not read the data directory.
    """
    from PIL import Image, ImageDraw

    from chatlog import _hex, _load_font
    from rooms import idle_thumbnail

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "chat-topics.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    bg = _hex("#0d0d1a")
    title_bg = _hex("#111133")
    card = _hex("#16162a")
    ink = _hex("#e8e6f4")
    meta = _hex("#9a98b8")
    accent = _hex("#88aaff")
    line = _hex("#223366")
    title_font = _load_font(20, bold=True)
    name_font = _load_font(15, bold=True)
    body = _load_font(13)
    small = _load_font(12)

    width = 780
    image = Image.new("RGB", (width, 720), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 42], fill=title_bg)
    draw.text((16, 10), "Topics", font=title_font, fill=accent)

    draw.text((16, 56), "cli-avatars", font=name_font, fill=accent)
    y = _topic_card(
        image, draw, 80, "hooks", "open", ["caine", "michimaru"], 1,
        card, ink, meta, body, small,
    )
    y = _topic_card(
        image, draw, y, "sprites", "waiting_on_user", ["michimaru"], 0,
        card, ink, meta, body, small,
    )
    draw.text((16, y + 6), "notes", font=name_font, fill=accent)
    y = _topic_card(
        image, draw, y + 30, "quiet", "done", ["bubble"], 0,
        card, ink, meta, body, small,
    )

    draw.text((16, y + 8), "Orchestrators", font=small, fill=meta)
    dots = [("Claude-west", "#4488ff"), ("Grok-north", "#4488ff"), ("Claude-east", "#aa44ff")]
    dx = 16
    dy = y + 30
    for name, color in dots:
        draw.ellipse([dx, dy + 3, dx + 10, dy + 13], fill=_hex(color))
        draw.text((dx + 16, dy), name, font=body, fill=ink)
        dx += int(body.getlength(name)) + 36

    header_top = dy + 36
    draw.line([12, header_top, width - 12, header_top], fill=line, width=1)
    draw.text((16, header_top + 10), "hooks", font=name_font, fill=ink)
    chip = STATUS_LABEL["open"]
    chip_w = int(small.getlength(chip)) + 16
    draw.rectangle([90, header_top + 10, 90 + chip_w, header_top + 28], fill=_hex(STATUS_COLOR["open"]))
    draw.text((98, header_top + 12), chip, font=small, fill=(255, 255, 255))
    draw.text(
        (16, header_top + 36),
        "Meet on the same window, eight pixels apart. Notes stay in this panel.",
        font=body, fill=ink,
    )
    pin_y = header_top + 62
    draw.text((16, pin_y), "Pinned", font=small, fill=meta)
    pin_y += 20
    for kind, text in (
        ("fact", "Perch is clear."),
        ("decision", "Same window? a: Same window"),
    ):
        draw.rectangle([16, pin_y, width - 16, pin_y + 28], fill=card)
        draw.text((24, pin_y + 6), f"{kind}  {text}", font=body, fill=ink)
        label = "Unpin"
        label_w = int(small.getlength(label)) + 16
        draw.rectangle([width - 24 - label_w, pin_y + 4, width - 24, pin_y + 24], fill=_hex("#334477"))
        draw.text((width - 16 - label_w, pin_y + 6), label, font=small, fill=(255, 255, 255))
        pin_y += 34
    draw.rectangle([16, pin_y, 70, pin_y + 22], fill=_hex("#334477"))
    draw.text((28, pin_y + 4), "Pin", font=small, fill=(255, 255, 255))
    draw.text((16, pin_y + 32), "Stored locally. Nothing here runs.", font=small, fill=meta)
    image.crop((0, 0, width, pin_y + 58)).save(target, format="PNG", optimize=True)
    return target


def _topic_card(image, draw, y, title, status, skins, decisions, card, ink, meta, body, small) -> int:
    from rooms import idle_thumbnail

    height = 64
    draw.rectangle([12, y, image.width - 13, y + height], fill=card)
    x = 24
    for skin in skins:
        sprite = idle_thumbnail(skin, 32)
        if sprite is not None:
            image.paste(sprite, (x, y + 16), sprite)
        x += 36
    draw.text((x + 8, y + 10), title, font=body, fill=ink)
    label = STATUS_LABEL[status]
    chip_x = x + 8 + int(body.getlength(title)) + 10
    chip_w = int(small.getlength(label)) + 14
    draw.rectangle([chip_x, y + 10, chip_x + chip_w, y + 28], fill=_hex_color(STATUS_COLOR[status]))
    draw.text((chip_x + 7, y + 12), label, font=small, fill=(20, 16, 40) if status == "waiting_on_user" else (255, 255, 255))
    extra = f"decisions {decisions}" if decisions else "no open decisions"
    draw.text((x + 8, y + 34), extra, font=small, fill=meta)
    return y + height + 8


def _hex_color(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def main() -> None:
    write_topics_preview()
    print("docs/media/chat-topics.png")


if __name__ == "__main__":
    main()
