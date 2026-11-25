"""TASKBACK.4: one ``emit:registry`` line in the card's topic for each agent update that wrote.

The line is display text in the existing channel record. It is data: never executed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Mapping, Sequence

from events import EventRejected, append_channel

SENDER = "emit:registry"


def describe(card: Mapping, events: Sequence[Mapping], actor: str) -> str:
    """``<actor> · <title>: doing → review, 60%, ticked <item> — <note>``."""
    parts, note = [], ""
    for event in events:
        kind = event["kind"]
        if kind == "moved":
            parts.append(f"{event['from']} → {event['to']}")
        elif kind == "progress":
            parts.append(f"{event['to']}%" if event.get("to") is not None else "progress cleared")
        elif kind == "checklist":
            parts.append(("ticked " if event.get("done") else "unticked ") + str(event.get("text", "")))
        elif kind == "learnt" and event.get("text"):
            parts.append(f"learnt: {event['text']}")
        if kind in ("progress", "status") and event.get("text"):
            note = str(event["text"])
    line = f"{actor} · {card['title']}: " + (", ".join(parts) or "note")
    return line + (f" — {note}" if note else "")


def post_update(directory: Path, card: Mapping, events: Sequence[Mapping], actor: str,
                timeout: float) -> None:
    """Append the line after the board lock is released (lock order: board, topics, channel).

    A summary rewrite (TASK-SUMMARY) comes every chat turn, so it posts no line of its own.
    """
    events = [e for e in events if e["kind"] != "summary"]
    if not events or card.get("topic") is None:
        return
    blocked = any(e["kind"] == "moved" and e.get("to") == "blocked" for e in events)
    entry = {"ts": time.time(), "from": SENDER, "to": SENDER, "channel": card["topic"],
             "icon": "warn" if blocked else "ok", "note": describe(card, events, actor)}
    try:
        append_channel(directory, entry, timeout=timeout)
    except (EventRejected, OSError):
        return  # the card is written; a busy channel only loses the notice
