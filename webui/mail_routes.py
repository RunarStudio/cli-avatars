"""MAILROOM phone routes: the letters (read), and with ``web.allow_writes`` post, retopic, approve and bounce.

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here.
"""

from __future__ import annotations

import re

import mailroom
from events import EventRejected
from topics import valid_topic_id

_ACTION = re.compile(r"^/api/mailroom/([0-9a-f]{16})/(approve|bounce|topic)$")
KEYS = ("id", "source", "ts", "text", "from", "room", "topic", "topic_title", "chat", "draft", "state")


def read(handler) -> None:
    """``GET /api/mailroom``: new letters, unsorted ones, held count, topics to file in, whether writes are on."""
    directory = handler.server.directory
    try:
        mailroom.ingest(directory)
    except (EventRejected, OSError):
        pass
    state = mailroom.public(directory)
    handler._json({"items": [_row(i) for i in state["items"]], "unsorted": [_row(i) for i in state["unsorted"]],
                   "count": state["count"], "held": state["held"], "topics": mailroom.topics(directory),
                   "writes": handler.server.writes()})


def write(handler, path: str, body: dict) -> None:
    directory = handler.server.directory
    if path == "/api/mailroom":
        if set(body) != {"text"} or not isinstance(body["text"], str) or not body["text"].strip():
            return handler._error(400)
        if len(body["text"]) > mailroom.TEXT_LIMIT:
            return handler._error(413)
        item = mailroom.post(directory, body["text"])
        return handler._json(_row({**item, "topic_title": item["topic"]})) if item else handler._error(400)
    found = _ACTION.match(path)
    if not found:
        return handler._error(404)
    item_id, verb = found.groups()
    if verb == "topic":
        if set(body) != {"topic"} or not valid_topic_id(body["topic"]):
            return handler._error(400)
        return handler._json({"ok": True}) if mailroom.retopic(directory, item_id, body["topic"]) \
            else handler._error(404)
    if body:
        return handler._error(400)
    if verb == "bounce":
        now = mailroom.bounce(directory, item_id)
        return handler._json({"ok": True, "now": now}) if now else handler._error(404)
    try:
        filed = mailroom.approve(directory, item_id)
    except EventRejected as exc:
        return handler._error(404 if exc.reason == "missing" else 409)
    if filed is None:
        return handler._error(404)
    return handler._json({"id": filed["card"]["id"], "topic": filed["card"]["topic"], "room": filed["room"],
                          "decision": (filed["decision"] or {}).get("id")})


def summary(directory) -> dict:
    """The SSE ``mailroom`` event: counts only, after taking in new lines."""
    try:
        mailroom.ingest(directory)
    except (EventRejected, OSError):
        pass
    return mailroom.counts(directory)


def _row(item: dict) -> dict:
    return {k: item.get(k) for k in KEYS}
