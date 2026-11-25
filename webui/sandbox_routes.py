"""SANDBOX phone routes: a task's sandbox (read), and with ``web.allow_writes`` Promote or Bin it.

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here. The phone sees the
branch and the worktree's folder name, never a path. It cannot make a sandbox: that is a desktop tap.
"""

from __future__ import annotations

import re

import sandbox
from events import EventRejected
from registry.facade import Registry

PATH = re.compile(r"^/api/cards/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/sandbox$")


def read(handler, card_id: str) -> None:
    """``GET /api/cards/<id>/sandbox``: ``sandbox`` (or null) and whether writes are on."""
    if _card(handler, card_id) is None:
        return handler._error(404)
    found = sandbox.view(sandbox.for_card(handler.server.directory, card_id))
    handler._json({"sandbox": found, "writes": handler.server.writes()})


def write(handler, card_id: str, body: dict) -> None:
    """``{"promote": true}``, ``{"bin": true}`` or ``{"bin": true, "confirm": true}``; 409 with ``why`` if refused."""
    directory = handler.server.directory
    if _card(handler, card_id) is None:
        return handler._error(404)
    row = sandbox.for_card(directory, card_id)
    if body == {"promote": True}:
        action = sandbox.promote
    elif body in ({"bin": True}, {"bin": True, "confirm": False}, {"bin": True, "confirm": True}):
        def action(d, sid):
            return sandbox.bin_sandbox(d, sid, confirm=body.get("confirm") is True)
    else:
        return handler._error(400)
    if row is None:
        return handler._json({"why": "This task has no sandbox."}, 409)
    try:
        action(directory, row["id"])
    except sandbox.Refused as exc:
        return handler._json({"why": exc.why, "dirty": isinstance(exc, sandbox.Dirty)}, 409)
    return read(handler, card_id)


def state(directory, card_id: str) -> str:
    """The card's sandbox state for the board list, ``""`` without one."""
    found = sandbox.for_card(directory, card_id)
    return found["state"] if found else ""


def summary(directory) -> tuple:
    """The SSE ``sandbox`` event fires when this changes."""
    return sandbox.stamp(directory)


def _card(handler, card_id: str) -> dict | None:
    try:
        return Registry(handler.server.directory).task_get(card_id)
    except (EventRejected, OSError):
        return None
