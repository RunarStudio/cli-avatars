"""STANDUP phone routes: the newest standup (read), and with ``web.allow_writes`` "Run standup now".

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here. The run is local
code (``standup.run``): no AI, no process. It is signed by the orchestrator of the last standup.
"""

from __future__ import annotations

import standup
from events import EventRejected


def read(handler) -> None:
    """``GET /api/standup``: the newest standup or null, the morning hour, whether writes are on."""
    handler._json({**standup.public(handler.server.directory), "writes": handler.server.writes()})


def write(handler, body: dict) -> None:
    """``POST /api/standup/run`` with ``{}``: today's standup again, pinned to the cards."""
    if body:
        return handler._error(400)
    directory = handler.server.directory
    last = standup.latest(directory) or {}
    try:
        made = standup.run(directory, lord=str(last.get("lord") or ""), lord_name=str(last.get("lord_name") or ""),
                           force=True)
    except (EventRejected, OSError):
        return handler._error(409)
    return handler._json({"standup": made})


def summary(directory) -> tuple:
    """The SSE ``standup`` event fires when this changes."""
    return standup.stamp(directory)
