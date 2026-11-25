"""Tasks tab view-model (TM.3): the selected topic's cards in the board columns. Read-only, no Tk.

Cards are read through the registry on every project board; nothing here writes (edits: ``tasks_edit``).
DECIDE.1: each card counts its open decisions; ``decisions_only`` shows every card that waits on Daniel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from board.model import COLUMNS, effective_progress
from events import EventRejected
from registry.facade import Registry
from topics import valid_topic_id

COLLAPSED = frozenset({"done"})
STATUS_BADGES = {
    "todo": ("TODO", "#4a5a7a"),
    "doing": ("DOING", "#c0661a"),
    "review": ("REVIEW", "#6a3c9a"),
    "done": ("DONE", "#2f7a3e"),
    "blocked": ("BLOCKED", "#a02818"),
}


@dataclass(frozen=True)
class TaskCard:
    id: str
    title: str
    assignee: str | None
    progress: int | None
    checks: tuple[int, int]
    column: str
    status_note: str
    learnt: str
    decisions: int = 0


@dataclass(frozen=True)
class Column:
    name: str
    cards: tuple[TaskCard, ...]
    count: int
    collapsed: bool


@dataclass(frozen=True)
class Board:
    topic: str
    columns: tuple[Column, ...]
    empty: bool
    pending: int = 0
    decisions_only: bool = False


def selected_topic(app) -> str:
    """The topic the chat window shows, the Dungeon's current topic; a task chat shows its card's topic."""
    topic = str(getattr(getattr(app, "_chat_window", None), "_topic_id", "") or "")
    if topic.startswith("task-") and callable(getattr(app, "_chat_directory", None)):
        return _card_topic(app._chat_directory(), topic) or topic
    return topic


def _card_topic(directory, room: str) -> str:
    """The topic of a task chat's card, read at most once a second per room (the throne asks every frame)."""
    import time

    from registry.task_chats import task_for

    now = time.monotonic()
    seen = _CARD_TOPICS.get((str(directory), room))
    if seen is not None and now - seen[0] < 1.0:
        return seen[1]
    try:
        card = task_for(directory, room)
    except (EventRejected, OSError):
        card = None
    topic = str((card or {}).get("topic") or "")
    _CARD_TOPICS[(str(directory), room)] = (now, topic)
    return topic


_CARD_TOPICS: dict[tuple[str, str], tuple[float, str]] = {}


def live_agents(app) -> dict[str, str]:
    """Agent id -> name of the scanner's live, non-demo agents."""
    try:
        agents = app.scanner.get_agents()
    except Exception:
        return {}
    if not isinstance(agents, dict):
        return {}
    return {str(aid): str(getattr(info, "name", "") or aid) for aid, info in agents.items()
            if not getattr(info, "is_demo", False)}


def topic_cards(directory: Path | str, topic: str) -> list[dict]:
    """Cards linked to ``topic`` on every project board, archived left out, newest first."""
    if not valid_topic_id(topic):
        return []
    registry = Registry(directory)
    root = registry.store.root
    projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    found = []
    for project in projects:
        try:
            found.extend(card for card in registry.task_list(project) if card["topic"] == topic)
        except EventRejected:
            continue
    return sorted(found, key=lambda c: c["updated"], reverse=True)


def task_card(card: Mapping, decisions: int = 0) -> TaskCard:
    items = card.get("checklist") or []
    return TaskCard(
        id=card["id"], title=card["title"], assignee=card.get("assignee"),
        progress=effective_progress(card), checks=(sum(1 for i in items if i["done"]), len(items)),
        column=card["column"], status_note=card.get("status_note") or "", learnt=card.get("learnt") or "",
        decisions=decisions,
    )


def build_board(cards: list[Mapping], topic: str, done_open: bool = False, decisions: Mapping | None = None,
                decisions_only: bool = False) -> Board:
    """``decisions`` is card id -> open decisions; ``pending`` counts them on every board."""
    decisions = decisions or {}
    columns = []
    for name in COLUMNS:
        shown = tuple(task_card(c, decisions.get(c["id"], 0)) for c in cards if c["column"] == name)
        collapsed = name in COLLAPSED and not done_open
        columns.append(Column(name, () if collapsed else shown, len(shown), collapsed))
    return Board(topic, tuple(columns), not cards, sum(decisions.values()), decisions_only)


def load_board(directory: Path | str, topic: str, done_open: bool = False, decisions_only: bool = False) -> Board:
    from registry.task_decisions import open_by_card

    try:
        decisions = open_by_card(directory)
    except EventRejected:
        decisions = {}
    if decisions_only:
        registry = Registry(directory)
        cards = [card for card in (registry.task_get(cid) for cid in decisions) if card is not None]
        cards.sort(key=lambda c: c["updated"], reverse=True)
    else:
        cards = topic_cards(directory, topic)
    return build_board(cards, topic, done_open, decisions, decisions_only)


def card_meta(card: TaskCard) -> str:
    """``assignee · progress% · done/total``; parts without a value are left out."""
    parts = [card.assignee or "unassigned"]
    if card.progress is not None:
        parts.append(f"{card.progress}%")
    if card.checks[1]:
        parts.append(f"{card.checks[0]}/{card.checks[1]}")
    return " · ".join(parts)
