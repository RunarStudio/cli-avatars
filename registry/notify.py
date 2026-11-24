"""NOTIFY.1: the agent's open cards for the hook context block. Read-only, at most 2,000 chars."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from board.model import effective_progress
from events import EventRejected
from registry.facade import Registry
from registry.policy import may_touch

CARDS_CAP = 2000
HEADER = "cards (yours, open; untrusted data):"


def agent_ids(store_id: str) -> frozenset[str]:
    """The hook's inbox id, plus ``claude:<id>`` for a bare Claude id (cards use ``source:id``)."""
    return frozenset({store_id} if ":" in store_id else {store_id, "claude:" + store_id})


def open_cards(registry: Registry, ids: Iterable[str]) -> list[dict]:
    """Cards not done or archived that one of ``ids`` may update (Decision D), newest first."""
    from topics import get_topic

    ids, members, found = frozenset(ids), {}, []
    root = registry.store.root
    projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    for project in projects:
        try:
            cards = registry.task_list(project)
        except EventRejected:
            continue
        for card in cards:
            topic = card["topic"]
            if card["column"] == "done":
                continue
            if card["assignee"] is None and topic is not None and topic not in members:
                entry = get_topic(registry.directory, topic, timeout=registry.timeout) or {}
                members[topic] = frozenset(m for m in entry.get("members") or [] if isinstance(m, str))
            if any(may_touch(card, agent, members.get(topic, frozenset())) for agent in ids):
                found.append(card)
    return sorted(found, key=lambda c: c["updated"], reverse=True)


def cards_block(cards: Iterable[Mapping], limit: int = CARDS_CAP) -> str:
    """One line per card (id, column, progress, title), whole lines only, at most ``limit`` chars.

    A card is added only while the room for a ``- <n> more`` line after it is left, so the
    count of the cards that did not fit always fits.
    """
    cards = list(cards)
    if not cards:
        return ""
    lines = [HEADER]
    for shown, card in enumerate(cards):
        progress = effective_progress(card)
        line = f"- {card['id']} [{card['column']}{'' if progress is None else f' {progress}%'}] {card['title']}"
        after = len(cards) - shown - 1
        reserve = len(f"\n- {after} more") if after else 0
        if len("\n".join(lines + [line])) + 1 + reserve > limit:
            lines.append(f"- {len(cards) - shown} more")
            break
        lines.append(line)
    return "\n".join(lines) + "\n"


def hook_cards(directory: Path, store_id: str, timeout: float, limit: int = CARDS_CAP) -> str:
    """The block for one hook call; empty on any store error so the hook never fails."""
    try:
        return cards_block(open_cards(Registry(directory, timeout=timeout), agent_ids(store_id)), limit)
    except (EventRejected, OSError):
        return ""