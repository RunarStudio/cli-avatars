"""GROK-CHAT phone routes: the Grok topics list (read) and **+ New Grok topic** (a write, behind the usual guards).

``GET /api/grok``: ``rows`` (room, kind, title, last line, time, turns, state; never a session id or a path) and
whether Grok can run (``ready``, ``why``). ``POST /api/grok/topics`` with ``{"bound": <room>}`` makes a Grok topic
bound to that room and answers ``{"room": …}``; it starts no CLI. Sending goes through ``POST /api/chat/<room>`` with
``"cli": "grok"``: the phone's confirm tap is Daniel's Enter.
"""

from __future__ import annotations

from chat_window import room_tools
from cli_avatars.app import grok_topics
from events import EventRejected
from topics import valid_topic_id


def read(handler) -> None:
    from cli_avatars.app import chat_clis
    from cli_avatars.model.room import load_binary_pin
    from cli_avatars.paths import config_path
    from rooms import load_config

    directory = handler.server.directory
    ready = chat_clis.template(load_config(config_path()), "grok") is not None
    why = "" if ready else "Grok: no command set (config.json chat.clis.grok)."
    if ready and load_binary_pin(directory, "grok") is None:
        why = "Confirm the Grok binary once in the Dungeon's chat (Use this binary), then send from here."
    rows = grok_topics.rows(directory, running=lambda room: room_tools().running(room, "grok"))
    handler._json({"rows": rows, "ready": ready, "why": why})


def write(handler, path: str, body: dict) -> None:
    if path != "/api/grok/topics":
        return handler._error(404)
    if set(body) != {"bound"} or not valid_topic_id(body["bound"]):
        return handler._error(400)
    try:
        room = grok_topics.new_topic(handler.server.directory, body["bound"])
    except (EventRejected, OSError):
        return handler._json({"why": f"Up to {grok_topics.MAX_TOPICS} Grok topics."}, 409)
    handler.server.actions._after_change()
    handler._json({"room": room})
