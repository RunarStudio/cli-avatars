"""Board cards and events (docs/board.md). Validation only; no I/O.

Card and event text is data. It is never executed, opened as a path, or fetched.
Validators drop unknown fields and raise ``EventRejected("schema")`` on a bad value.
"""

from __future__ import annotations

import re
import time
import unicodedata
import uuid
from datetime import datetime
from typing import Mapping

from events import UUID_RE, EventRejected, sanitize_text
from inbox import valid_agent_id
from topics import clean_project, valid_topic_id

COLUMNS = ("todo", "doing", "review", "done", "blocked")
KINDS = ("created", "edited", "moved", "assigned", "commented", "checklist", "linked_pr", "prompt")
PROMPT_TARGETS = ("claude", "grok", "both")
PROMPT_OUTCOMES = ("ok", "error", "stopped", "timeout")
PERSON = "daniel"

TITLE_LIMIT = 120
BODY_LIMIT = 4000
CHECK_TEXT_LIMIT = 240
EVENT_TEXT_LIMIT = 2000
MAX_LABELS = 8
MAX_CHECKLIST = 20
MAX_NOTIFY = 8
MAX_HISTORY = 200

_LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_MACHINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
_PR = re.compile(r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+/pull/[1-9][0-9]{0,9}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
_DEVICE = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))})


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean_board_project(value: object) -> str:
    """``clean_project`` that also rejects hidden names and Windows device names, with or without extension."""
    project = clean_project(value)
    if project.startswith(".") or project.split(".")[0].strip().upper() in _DEVICE:
        raise EventRejected("schema")
    return project


def valid_uuid(value: object) -> bool:
    return isinstance(value, str) and value == value.lower() and UUID_RE.fullmatch(value) is not None


def valid_ts(value: object) -> bool:
    if not isinstance(value, str) or _TS.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value[:-1])
    except ValueError:
        return False
    return True


def valid_assignee(value: object) -> bool:
    """An agent id, ``agent@machine``, or ``daniel``; the chat store's ``user`` is not a board id."""
    if value == PERSON:
        return True
    if not isinstance(value, str) or value == "user":
        return False
    agent, at, machine = value.partition("@")
    if at:
        return agent != "user" and valid_agent_id(agent) and _MACHINE.fullmatch(machine) is not None
    return valid_agent_id(value)


def sanitize_body(value: object, limit: int = BODY_LIMIT) -> str:
    """``sanitize_text`` that keeps newlines."""
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    kept = (ch for ch in text if ch == "\n" or unicodedata.category(ch) not in {"Cc", "Cf", "Cs"})
    return "".join(kept).strip()[:limit]


def _reject() -> EventRejected:
    return EventRejected("schema")


def validate_event(obj: object) -> dict[str, object]:
    if not isinstance(obj, Mapping):
        raise _reject()
    ident, ts, card = obj.get("id"), obj.get("ts"), obj.get("card")
    actor, kind = obj.get("actor"), obj.get("kind")
    if not valid_uuid(ident) or not valid_ts(ts) or kind not in KINDS:
        raise _reject()
    if card is not None and not valid_uuid(card):
        raise _reject()
    if not valid_assignee(actor):
        raise _reject()
    out: dict[str, object] = {"id": ident, "ts": ts, "card": card, "actor": actor, "kind": kind}
    for key in ("from", "to"):
        if obj.get(key) is not None:
            value = obj[key]
            if value not in COLUMNS and not valid_assignee(value):
                raise _reject()
            out[key] = value
    if obj.get("text") is not None:
        out["text"] = sanitize_body(obj["text"], EVENT_TEXT_LIMIT)
    if obj.get("notify") is not None:
        notify = obj["notify"]
        if not isinstance(notify, list) or len(notify) > MAX_NOTIFY or not all(map(valid_assignee, notify)):
            raise _reject()
        out["notify"] = list(notify)
    if kind == "prompt":
        room, target, outcome = obj.get("room"), obj.get("target"), obj.get("outcome")
        if not valid_topic_id(room) or target not in PROMPT_TARGETS or outcome not in PROMPT_OUTCOMES:
            raise _reject()
        out.update(room=room, target=target, outcome=outcome)
    return out


def validate_card(obj: object) -> dict[str, object]:
    if not isinstance(obj, Mapping):
        raise _reject()
    ident = obj.get("id")
    title = sanitize_text(obj.get("title"), TITLE_LIMIT)
    project = clean_board_project(obj.get("project"))
    if not valid_uuid(ident) or not title or not project or obj.get("column") not in COLUMNS:
        raise _reject()
    if not valid_ts(obj.get("created")) or not valid_ts(obj.get("updated")):
        raise _reject()
    card: dict[str, object] = {
        "id": ident,
        "title": title,
        "body": sanitize_body(obj.get("body", "")),
        "topic": obj.get("topic"),
        "project": project,
        "assignee": obj.get("assignee"),
        "column": obj["column"],
        "labels": obj.get("labels", []),
        "pr": obj.get("pr"),
        "checklist": [],
        "created": obj["created"],
        "updated": obj["updated"],
        "history": [],
    }
    if card["topic"] is not None and not valid_topic_id(card["topic"]):
        raise _reject()
    if card["assignee"] is not None and not valid_assignee(card["assignee"]):
        raise _reject()
    labels = card["labels"]
    if not isinstance(labels, list) or len(labels) > MAX_LABELS:
        raise _reject()
    if not all(isinstance(v, str) and _LABEL.fullmatch(v) for v in labels):
        raise _reject()
    if card["pr"] is not None and not (isinstance(card["pr"], str) and _PR.fullmatch(card["pr"])):
        raise _reject()
    checklist = obj.get("checklist", [])
    if not isinstance(checklist, list) or len(checklist) > MAX_CHECKLIST:
        raise _reject()
    for item in checklist:
        if not isinstance(item, Mapping) or type(item.get("done")) is not bool:
            raise _reject()
        text = sanitize_text(item.get("text"), CHECK_TEXT_LIMIT)
        if not text:
            raise _reject()
        card["checklist"].append({"text": text, "done": item["done"]})
    history = obj.get("history", [])
    if not isinstance(history, list):
        raise _reject()
    card["history"] = [validate_event(e) for e in history[-MAX_HISTORY:]]
    return card


def new_card(project: str, title: str, body: str = "", topic: str | None = None,
             labels: list[str] | None = None, assignee: str | None = None) -> dict[str, object]:
    """A validated card in ``todo`` with a fresh id."""
    ts = now_ts()
    return validate_card({
        "id": str(uuid.uuid4()), "title": title, "body": body, "topic": topic, "project": project,
        "assignee": assignee, "column": "todo", "labels": labels or [], "created": ts, "updated": ts,
    })


def new_event(kind: str, actor: str, card: str | None = None, **fields: object) -> dict[str, object]:
    """A validated event with a fresh id and the current time."""
    return validate_event({"id": str(uuid.uuid4()), "ts": now_ts(), "card": card, "actor": actor,
                           "kind": kind, **fields})
