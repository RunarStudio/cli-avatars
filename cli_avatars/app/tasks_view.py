"""Tasks tab view-model (TM.3): the selected topic's cards in the board columns. Read-only, no Tk.

Cards are read through the registry on every project board; nothing here writes (edits: ``tasks_edit``).
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


@dataclass(frozen=True)
class TaskCard:
    id: str
    title: str
    assignee: str | None
    progress: int | None
    checks: tuple[int, int]


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


def selected_topic(app) -> str:
    """The topic the chat window shows, the Dungeon's current topic."""
    return str(getattr(getattr(app, "_chat_window", None), "_topic_id", "") or "")


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


def task_card(card: Mapping) -> TaskCard:
    items = card.get("checklist") or []
    return TaskCard(
        id=card["id"], title=card["title"], assignee=card.get("assignee"),
        progress=effective_progress(card), checks=(sum(1 for i in items if i["done"]), len(items)),
    )


def build_board(cards: list[Mapping], topic: str, done_open: bool = False) -> Board:
    columns = []
    for name in COLUMNS:
        shown = tuple(task_card(c) for c in cards if c["column"] == name)
        collapsed = name in COLLAPSED and not done_open
        columns.append(Column(name, () if collapsed else shown, len(shown), collapsed))
    return Board(topic, tuple(columns), not cards)


def load_board(directory: Path | str, topic: str, done_open: bool = False) -> Board:
    return build_board(topic_cards(directory, topic), topic, done_open)


def card_meta(card: TaskCard) -> str:
    """``assignee · progress% · done/total``; parts without a value are left out."""
    parts = [card.assignee or "unassigned"]
    if card.progress is not None:
        parts.append(f"{card.progress}%")
    if card.checks[1]:
        parts.append(f"{card.checks[0]}/{card.checks[1]}")
    return " · ".join(parts)
