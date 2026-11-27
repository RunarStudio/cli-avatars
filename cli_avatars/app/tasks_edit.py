"""KANBAN.1: Daniel's card edits from the Tasks tab. No Tk.

Every write goes through ``Registry`` with the actor ``daniel``. Fields are checked here first,
so a bad value comes back as a field error and nothing is written. Card text is data: it is
stored and shown, never run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from board.model import (
    BODY_LIMIT,
    CHECK_TEXT_LIMIT,
    COLUMNS,
    EVENT_TEXT_LIMIT,
    LEARNT_LIMIT,
    MAX_CHATS,
    MAX_CHECKLIST,
    MAX_LABELS,
    PERSON,
    STATUS_NOTE_LIMIT,
    TITLE_LIMIT,
    valid_assignee,
    valid_label,
)
from chatlog import format_stamp
from events import EventRejected
from registry.facade import Registry
from topics import get_topic, valid_topic_id

_REASONS = {
    "missing": "That card or topic is gone.",
    "schema": "The board refused that change.",
    "io": "The board file could not be written.",
    "timeout": "The board is busy; try again.",
    "answered": "That decision is already answered.",
}


@dataclass(frozen=True)
class Outcome:
    card: dict | None = None
    errors: Mapping[str, str] = field(default_factory=dict)
    event: str | None = None


def _too_long(text: str, limit: int) -> str | None:
    return f"At most {limit} characters ({len(text)})." if len(text) > limit else None


def parse_labels(text: str) -> tuple[list[str], str | None]:
    """Comma or space separated, lowercased; an error names the first bad label."""
    labels = [part.lower() for part in re.split(r"[,\s]+", text or "") if part]
    if len(labels) > MAX_LABELS:
        return labels, f"At most {MAX_LABELS} labels."
    for label in labels:
        if not valid_label(label):
            return labels, f"'{label[:32]}': a-z, 0-9, - and _ only, 32 characters."
    return list(dict.fromkeys(labels)), None


def _title_error(title: str) -> str | None:
    if not title.strip():
        return "A title is needed."
    return _too_long(title.strip(), TITLE_LIMIT)


class TaskEditor:
    """Edits for the cards of ``topic``; new cards go to the topic's project board."""

    def __init__(self, directory: Path | str, topic: str) -> None:
        self.directory = directory
        self.topic = topic
        self.registry = Registry(directory)

    def create(self, title: str, body: str = "", labels: str = "") -> Outcome:
        found, errors = parse_labels(labels)
        errors = {k: v for k, v in (("title", _title_error(title)), ("body", _too_long(body, BODY_LIMIT)),
                                    ("labels", errors)) if v}
        if errors:
            return Outcome(errors=errors)
        project = self._project()
        if not project:
            return Outcome(errors={"form": "Pick a topic first."})
        return self._run(lambda: self.registry.task_create(project, title.strip(), body, self.topic, found),
                         "created")

    def edit(self, card_id: str, *, title: str | None = None, body: str | None = None,
             labels: str | None = None, topic: str | None = None) -> Outcome:
        changes: dict[str, object] = {}
        errors: dict[str, str] = {}
        if title is not None:
            errors["title"] = _title_error(title)
            changes["title"] = title.strip()
        if body is not None:
            errors["body"] = _too_long(body, BODY_LIMIT)
            changes["body"] = body
        if labels is not None:
            changes["labels"], errors["labels"] = parse_labels(labels)
        if topic is not None:
            topic = topic.strip()
            errors["topic"] = self._topic_error(topic)
            changes["topic"] = topic or None
        errors = {k: v for k, v in errors.items() if v}
        if errors:
            return Outcome(errors=errors)
        return self._run(lambda: self.registry.task_edit(card_id, **changes), "edited")

    def move(self, card_id: str, column: str) -> Outcome:
        if column not in COLUMNS:
            return Outcome(errors={"column": "Unknown column."})
        return self._run(lambda: self.registry.task_move(card_id, column), "moved")

    def assign(self, card_id: str, assignee: str) -> Outcome:
        value = assignee.strip() or None
        if value is not None and not valid_assignee(value):
            return Outcome(errors={"assignee": "Not an agent id or daniel."})
        return self._run(lambda: self.registry.task_assign(card_id, value), "assigned")

    def check_add(self, card_id: str, text: str) -> Outcome:
        text = text.strip()
        error = "Write the item first." if not text else _too_long(text, CHECK_TEXT_LIMIT)
        if error:
            return Outcome(errors={"check": error})

        def add(card):
            if len(card["checklist"]) >= MAX_CHECKLIST:
                raise EventRejected("schema")
            return {**card, "checklist": card["checklist"] + [{"text": text, "done": False}]}

        return self._run(lambda: self.registry.change(card_id, add, PERSON), "edited")

    def check_tick(self, card_id: str, index: int, done: bool) -> Outcome:
        def tick(card):
            items = [dict(item) for item in card["checklist"]]
            if not 0 <= index < len(items):
                raise EventRejected("schema")
            items[index]["done"] = bool(done)
            return {**card, "checklist": items}

        return self._run(lambda: self.registry.change(card_id, tick, PERSON), "checklist")

    def progress(self, card_id: str, value: str, note: str | None) -> Outcome:
        """``value`` "" means use the checklist ratio; ``note`` None keeps the status note."""
        value = value.strip().rstrip("%")
        if value and not (value.isdigit() and int(value) <= 100):
            return Outcome(errors={"progress": "A whole number 0-100, or empty for the checklist."})
        if note is not None and _too_long(note, STATUS_NOTE_LIMIT):
            return Outcome(errors={"note": _too_long(note, STATUS_NOTE_LIMIT)})
        number = int(value) if value else None
        return self._run(lambda: self.registry.task_progress(card_id, number, note), "progress")

    def status(self, card_id: str, note: str) -> Outcome:
        error = _too_long(note, STATUS_NOTE_LIMIT)
        if error:
            return Outcome(errors={"note": error})
        return self._run(lambda: self.registry.change(card_id, lambda c: {**c, "status_note": note}, PERSON),
                         "status")

    def learnt(self, card_id: str, text: str) -> Outcome:
        """What we learnt, asked when the card lands in done."""
        error = "Write what we learnt, or Skip." if not text.strip() else _too_long(text.strip(), LEARNT_LIMIT)
        if error:
            return Outcome(errors={"learnt": error})
        return self._run(lambda: self.registry.task_learnt(card_id, text), "learnt")

    def comment(self, card_id: str, text: str) -> Outcome:
        error = "Write the comment first." if not text.strip() else _too_long(text, EVENT_TEXT_LIMIT)
        if error:
            return Outcome(errors={"comment": error})

        def post():
            self.registry.task_comment(card_id, text)
            return self.registry.task_get(card_id)

        return self._run(post, "commented")

    def archive(self, card_id: str) -> Outcome:
        return self._run(lambda: self.registry.task_archive(card_id), "edited")

    def chat_new(self, card_id: str, cli: str) -> Outcome:
        """TASK-CHAT.1: a new chat on the card, its room ready. No CLI starts until Enter in that chat."""
        from registry.task_chats import cli_ready, start_chat

        ready, why = cli_ready(cli)
        if not ready:
            return Outcome(errors={"chats": why})
        card = self.registry.task_get(card_id)
        if card is not None and len(card["chats"]) >= MAX_CHATS:
            return Outcome(errors={"chats": f"Up to {MAX_CHATS} chats per task."})
        return self._run(lambda: start_chat(self.registry, card_id, cli)[0], "chat")

    def decide(self, card_id: str, decision_id: str, choice: str | None = None, text: str = "") -> Outcome:
        """DECIDE.1: Daniel answers a decision on the card: an option, free text, or both."""
        from decisions import ANSWER_LIMIT

        text = (text or "").strip()
        error = "Pick an option or write an answer." if choice is None and not text else _too_long(text, ANSWER_LIMIT)
        if error:
            return Outcome(errors={"decide": error})

        def answer():
            self.registry.decision_answer(decision_id, choice, text or None)
            return self.registry.task_get(card_id)

        return self._run(answer, "decision")

    def _project(self) -> str:
        if not valid_topic_id(self.topic):
            return ""
        entry = get_topic(self.directory, self.topic, timeout=self.registry.timeout)
        if entry is None:
            return ""
        return str(entry.get("project") or self.topic)

    def _topic_error(self, topic: str) -> str | None:
        if not topic:
            return None
        if not valid_topic_id(topic) or get_topic(self.directory, topic, timeout=self.registry.timeout) is None:
            return "No topic with that id."
        return None

    def _run(self, write: Callable[[], dict], event: str) -> Outcome:
        try:
            card = write()
        except EventRejected as exc:
            return Outcome(errors={"form": _REASONS.get(exc.reason, _REASONS["schema"])})
        except OSError:
            return Outcome(errors={"form": _REASONS["io"]})
        return Outcome(card=card, event=event)


def assignee_choices(directory: Path | str, topic: str, live: Mapping[str, str]) -> list[tuple[str, str]]:
    """``(value, label)``: nobody, daniel, the topic's members, then live agents by name."""
    members: list[str] = []
    if valid_topic_id(topic):
        entry = get_topic(directory, topic) or {}
        found = entry.get("members")
        members = [m for m in found if isinstance(m, str)] if isinstance(found, list) else []
    choices = [("", "unassigned"), (PERSON, PERSON)]
    for agent in [*live, *members]:
        if valid_assignee(agent) and agent != PERSON and agent not in (v for v, _ in choices):
            choices.append((agent, str(live.get(agent) or agent)))
    return choices


def chat_rows(directory: Path | str, card: Mapping) -> list[dict]:
    """The card's chats, oldest first: room, CLI, ``MM-DD HH:MM`` started, the room's last said line, ``pack``."""
    from context_packs import started_with
    from topics import topic_messages

    rows = []
    for chat in card.get("chats") or []:
        try:
            lines = topic_messages(directory, chat["room"])
        except (EventRejected, OSError):
            lines = []
        said = [m for m in lines if m.get("icon") == "speech"] or lines
        last = str(said[-1].get("text") or "") if said else ""
        rows.append({"room": chat["room"], "cli": chat["cli"], "started": format_stamp(chat["created"]),
                     "last": (last if len(last) <= 80 else last[:79] + "…") or "no messages yet",
                     "pack": started_with(directory, chat["room"])})
    return rows


def _line(event: Mapping) -> str:
    kind, before, after = event["kind"], event.get("from"), event.get("to")
    text = event.get("text") or ""
    if kind == "moved":
        return f"moved {before} → {after}"
    if kind == "assigned":
        return f"assigned {after or 'nobody'}"
    if kind == "commented":
        return f"{event['actor']}: {text}"
    if kind == "checklist":
        return f"{'ticked' if event.get('done') else 'unticked'} {text}".strip()
    if kind == "progress":
        return f"progress {before if before is not None else 'auto'} → {after if after is not None else 'auto'}"
    if kind == "status":
        return f"status: {text}"
    if kind == "learnt":
        return f"learnt: {text}"
    if kind == "chat":
        return f"new {event.get('target')} chat"
    if kind == "decision":
        return text
    return kind


def history_lines(card: Mapping, limit: int = 8) -> list[str]:
    """Newest first: ``MM-DD HH:MM actor what``; a comment reads ``actor: text``."""
    lines = []
    for event in reversed(card.get("history") or []):
        if event["kind"] == "summary":  # rewritten every chat turn; the card shows it on top
            continue
        stamp = format_stamp(event["ts"])
        what = _line(event)
        lines.append(f"{stamp} {what}" if event["kind"] == "commented" else f"{stamp} {event['actor']} {what}")
        if len(lines) == limit:
            break
    return lines
