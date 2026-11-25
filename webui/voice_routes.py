"""PHONE-VOICE phone routes (reads only): what a transcript would do, and the spoken summary line.

``GET /api/voice/parse?q=&decision=&current=`` maps the browser's transcript (``voice.parse``) and, for a new task,
ranks topics with the quick-capture ranker. ``GET /api/voice/summary[?task=]`` is the task's line or the needs-you
count; in focus another task's line is held. The phone confirms through the existing writes (decision answer,
capture): nothing here writes, and no CLI starts.
"""

from __future__ import annotations

import focus
import needs_you
import voice
from board.model import valid_uuid
from registry.facade import Registry
from topics import valid_topic_id
from webui import scene

TOPICS_MAX = 3


def read(handler, path: str, query) -> None:
    if path == "/api/voice/parse":
        return _parse(handler, query)
    if path == "/api/voice/summary":
        return _summary(handler, query)
    handler._error(404)


def _parse(handler, query) -> None:
    from registry import capture

    directory = handler.server.directory
    text = (query.get("q") or [""])[0][:voice.MAX_TEXT]
    wanted = (query.get("decision") or [""])[0].lower()
    decision = next((d for d in scene.decisions(directory) if d["id"] == wanted), None) if wanted else None
    action = voice.parse(text, decision)
    topics = []
    if action["kind"] == "task":
        current = (query.get("current") or [""])[0]
        index = capture.build_index(directory)
        topics = [{"id": t, "title": index.title(t)}
                  for t in index.rank(action["title"], current if valid_topic_id(current) else "")[:TOPICS_MAX]]
    handler._json({"action": action, "decision": decision["id"] if decision and action["kind"] == "answer" else None,
                   "topics": topics, "writes": handler.server.writes()})


def _summary(handler, query) -> None:
    directory = handler.server.directory
    task = (query.get("task") or [""])[0]
    held_by = focus.current(directory)
    if task:
        if not valid_uuid(task):
            return handler._error(400)
        card = Registry(directory).task_get(task)
        if card is None:
            return handler._error(404)
        if held_by and held_by != task:
            return handler._json({"line": f"Held: focus is on {focus.public(directory)['title']}.", "held": True})
        return handler._json({"line": voice.task_line(card), "held": False})
    rows = [r for r in needs_you.pending(directory) if held_by is None or focus.belongs(r, held_by)]
    handler._json({"line": voice.needs_line(rows), "held": False})
