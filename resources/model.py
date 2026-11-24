"""Resource records (TM.1): a link, a file path or a note on a topic. Validation only; no I/O.

A resource is data. Its url is never fetched, its path never opened, its body never run.
Validators drop unknown fields and raise ``EventRejected("schema")`` on a bad value.
Title and body get the shared secret redaction (``redaction.redact``) before sanitising.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Mapping
from urllib.parse import urlsplit

from board.model import now_ts, sanitize_body, valid_assignee, valid_ts, valid_uuid
from events import EventRejected, sanitize_text
from redaction import redact
from topics import valid_topic_id

KINDS = ("link", "file", "note")
PAYLOAD = {"link": "url", "file": "path", "note": "body"}
TITLE_LIMIT = 120
BODY_LIMIT = 4000
URL_LIMIT = 2048
PATH_LIMIT = 260

_DRIVE = re.compile(r"^[A-Za-z]:")


def _reject() -> EventRejected:
    return EventRejected("schema")


def _has_controls(value: str) -> bool:
    return any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in value)


def clean_url(value: object) -> str:
    """An https URL with a host and no userinfo, kept as given. It is never fetched."""
    if not isinstance(value, str) or not value or len(value) > URL_LIMIT:
        raise _reject()
    if _has_controls(value) or any(ch.isspace() or ch == "\\" for ch in value):
        raise _reject()
    try:
        parts = urlsplit(value)
        host, _port = parts.hostname, parts.port
    except ValueError:
        raise _reject() from None
    if parts.scheme != "https" or not host or "@" in parts.netloc:
        raise _reject()
    return value


def clean_path(value: object) -> str:
    """A relative path with ``/`` separators: no root, drive, UNC, ``~``, ``:`` or ``..``. Never opened."""
    if not isinstance(value, str) or len(value) > PATH_LIMIT or _has_controls(value):
        raise _reject()
    path = value.strip().replace("\\", "/")
    if not path or path.startswith(("/", "~")) or _DRIVE.match(path) or ":" in path:
        raise _reject()
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise _reject()
    return "/".join(parts)


def _clean_body(value: object) -> str:
    if not isinstance(value, str) or len(value) > BODY_LIMIT:
        raise _reject()
    body = sanitize_body(redact(value), BODY_LIMIT)
    if not body:
        raise _reject()
    return body


_CLEAN = {"url": clean_url, "path": clean_path, "body": _clean_body}


def validate_resource(obj: object) -> dict[str, object]:
    """The stored record: common fields plus the one payload field of its kind."""
    if not isinstance(obj, Mapping):
        raise _reject()
    kind = obj.get("kind")
    if kind not in KINDS:
        raise _reject()
    field = PAYLOAD[kind]
    if any(obj.get(other) is not None for other in PAYLOAD.values() if other != field):
        raise _reject()
    title = sanitize_text(redact(obj["title"]) if isinstance(obj.get("title"), str) else None, TITLE_LIMIT)
    ident, topic, card, by = obj.get("id"), obj.get("topic_id"), obj.get("card_id"), obj.get("added_by")
    if not valid_uuid(ident) or not valid_topic_id(topic) or not title or not valid_assignee(by):
        raise _reject()
    if card is not None and not valid_uuid(card):
        raise _reject()
    if not valid_ts(obj.get("created_at")) or not valid_ts(obj.get("updated_at")):
        raise _reject()
    return {
        "id": ident, "topic_id": topic, "card_id": card, "kind": kind, "title": title,
        field: _CLEAN[field](obj.get(field)), "added_by": by,
        "created_at": obj["created_at"], "updated_at": obj["updated_at"],
    }


def new_resource(topic_id: str, kind: str, title: str, *, added_by: str, url: str | None = None,
                 path: str | None = None, body: str | None = None, card_id: str | None = None) -> dict[str, object]:
    """A validated resource with a fresh id and both timestamps now."""
    ts = now_ts()
    return validate_resource({
        "id": str(uuid.uuid4()), "topic_id": topic_id, "card_id": card_id, "kind": kind, "title": title,
        "url": url, "path": path, "body": body, "added_by": added_by, "created_at": ts, "updated_at": ts,
    })
