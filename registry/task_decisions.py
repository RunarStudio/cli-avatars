"""DECIDE.1: decisions an agent asks Daniel on a task card. No Tk, and nothing here starts a CLI.

A task decision is a ``decisions.py`` record with ``card`` set, asked in a room: the card's topic, or
the task chat that asked. While one is open the card's topic is ``waiting_on_user`` (Decision F). The
answer goes to the asker's inbox and the room, writes a ``decision`` event on the card, and puts the
topic back to ``open`` once no decision in it is open. Question, options and answer are data: never run.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from board.model import PERSON, new_event, valid_chat_room
from decisions import LETTERS, OPTION_LIMIT, QUESTION_LIMIT, answer_decision, ask_decision, list_decisions
from events import EventRejected, directory_lock, sanitize_text
from redaction import redact
from registry.policy import ARCHIVED_LABEL, scrub_paths

OPEN, WAITING = "open", "waiting_on_user"
PUBLIC = ("id", "ts", "from", "room", "question", "options", "card", "title", "topic", "project", "column")


def clean_text(value: object, limit: int) -> str:
    """Agent text: redacted, paths hashed, sanitised, at most ``limit``. Empty is ``schema``."""
    if not isinstance(value, str):
        raise EventRejected("schema")
    text = sanitize_text(scrub_paths(redact(sanitize_text(value, 4 * limit))), limit)
    if not text:
        raise EventRejected("schema")
    return text


def clean_options(values: object) -> list[str]:
    """``a=<label>`` strings for ``ask_decision``: none, or two to six labels."""
    if values is None or values == []:
        return []
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not 2 <= len(values) <= len(LETTERS):
        raise EventRejected("schema")
    return [f"{letter}={clean_text(value, OPTION_LIMIT)}" for letter, value in zip(LETTERS, values, strict=False)]


def check_card(card: Mapping) -> None:
    """Only a live card with a room is asked on: not done, not archived, with a topic."""
    if card["column"] == "done" or ARCHIVED_LABEL in card["labels"] or not card.get("topic"):
        raise EventRejected("not_allowed")


def ask(registry, agent: str, card: Mapping, question: object, options: object = None, *,
        room: str | None = None, via: str = "mcp") -> dict:
    """Store the decision, note it on the card, set the topic waiting. The caller checked the agent's right."""
    check_card(card)
    text = clean_text(question, QUESTION_LIMIT)
    record = ask_decision(registry.directory, agent=agent, room=room or card["topic"], question=text,
                          options=clean_options(options), card=card["id"], timeout=registry.timeout)
    registry.store.append_event(new_event("decision", agent, card["id"], text=f"asks: {text}", via=via),
                                timeout=registry.timeout)
    _flip(registry, card["topic"], OPEN, WAITING)
    return record


def answer(registry, decision_id: str, choice: str | None = None, text: object = None) -> dict:
    """Daniel's answer: to the asker's inbox and room, on the card, and the topic open again when none waits."""
    reply = answer_decision(registry.directory, decision_id, choice, text=text, timeout=registry.timeout)
    row = next((r for r in list_decisions(registry.directory) if r["id"] == reply["decision_id"]), {})
    card = registry.task_get(row["card"]) if row.get("card") else None
    if card is not None:
        registry.store.append_event(new_event("decision", PERSON, card["id"], text=f"answered: {reply['text']}"),
                                    timeout=registry.timeout)
        topic = card.get("topic")
        if topic and not any(p["topic"] == topic or p["room"] == topic for p in pending(registry.directory)):
            _flip(registry, topic, WAITING, OPEN)
    return reply


def pending(directory: Path | str) -> list[dict]:
    """Open decisions on live cards, oldest first, each with its card's title, topic, project and column."""
    from registry.facade import Registry

    registry = Registry(directory)
    found = []
    for row in list_decisions(directory, open_only=True):
        card = registry.task_get(row["card"]) if row.get("card") else None
        if card is None or ARCHIVED_LABEL in card["labels"]:
            continue
        found.append({**row, "title": card["title"], "topic": card["topic"], "project": card["project"],
                      "column": card["column"]})
    return found


def open_by_card(directory: Path | str) -> dict[str, int]:
    return dict(Counter(row["card"] for row in pending(directory)))


def for_card(directory: Path | str, card_id: str) -> list[dict]:
    """Every decision on one card, open and answered, oldest first."""
    return [row for row in list_decisions(directory) if row.get("card") == card_id]


def said(row: Mapping) -> str:
    """The answer as one line: the chosen label, then Daniel's note."""
    labels = {o["letter"]: o["text"] for o in row.get("options") or []}
    return ": ".join(part for part in (labels.get(row.get("choice") or ""), row.get("answer")) if part)


def public(row: Mapping) -> dict:
    """The phone's view of one pending decision; ``chat`` is true when a task chat asked."""
    return {**{key: row.get(key) for key in PUBLIC}, "chat": valid_chat_room(row.get("room"))}


def _flip(registry, topic: str, old: str, new: str) -> None:
    """``old`` -> ``new`` under the topics lock; any other status (``done``) stays."""
    from topics import _existing_root, _read_one, _write_one

    root = _existing_root(registry.directory)
    if root is None:
        return
    with directory_lock(root, timeout=registry.timeout):
        entry = _read_one(root, topic)
        if entry is None or entry.get("status") != old:
            return
        entry["status"] = new
        entry["updated"] = time.time()
        _write_one(root, entry)
