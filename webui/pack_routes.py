"""CONTEXT-PACKS phone routes: a task's pack (read), and with ``web.allow_writes`` pin or unpin a line.

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here.
"""

from __future__ import annotations

import re

import context_packs
from events import EventRejected
from registry.facade import Registry

PATH = re.compile(r"^/api/cards/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/pack$")


def read(handler, card_id: str) -> None:
    """``GET /api/cards/<id>/pack``: the four parts, size and limit, whether writes are on."""
    card = _card(handler, card_id)
    if card is None:
        return handler._error(404)
    handler._json({**context_packs.build(handler.server.directory, card), "writes": handler.server.writes()})


def write(handler, card_id: str, body: dict) -> None:
    """``{"pin": {"part", "text"}}`` or ``{"unpin": "<key>"}``; answers the pack as it is now."""
    directory = handler.server.directory
    if _card(handler, card_id) is None:
        return handler._error(404)
    if set(body) == {"pin"} and isinstance(body["pin"], dict) and set(body["pin"]) == {"part", "text"}:
        done = context_packs.pin(directory, card_id, body["pin"]["part"], body["pin"]["text"])
    elif set(body) == {"unpin"} and isinstance(body["unpin"], str):
        done = context_packs.unpin(directory, card_id, body["unpin"])
    else:
        return handler._error(400)
    return read(handler, card_id) if done else handler._error(400)


def summary(directory) -> tuple:
    """The SSE ``pack`` event fires when this changes."""
    return context_packs.stamp(directory)


def _card(handler, card_id: str) -> dict | None:
    try:
        return Registry(handler.server.directory).task_get(card_id)
    except (EventRejected, OSError):
        return None
