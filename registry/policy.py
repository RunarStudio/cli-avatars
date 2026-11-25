"""What an agent may change (decisions B, C, D, E, F, K). Pure: no I/O, no clock.

Every refusal is ``EventRejected`` with a short reason:

- ``not_agent``: the caller id is not an agent (``daniel``, ``user`` or malformed).
- ``not_owner``: the card is assigned to someone else, or unassigned in a topic the agent is not in.
- ``not_allowed``: the move, topic status or field is not open to agents.
- ``switched_off``: ``task_propose`` while ``registry.agents_may_create`` is false, outside an
  orchestrator room's own topic (ORCH.ROOM).
- ``rate_limited``: over 30 writes a minute, 300 an hour, or 5 proposals an hour.
"""

from __future__ import annotations

import hashlib
import re
from typing import Collection, Mapping, Sequence

from board.model import PERSON, valid_assignee
from events import EventRejected, sanitize_text

AGENT_MOVES: dict[str, frozenset[str]] = {
    "todo": frozenset({"doing"}),
    "doing": frozenset({"review", "blocked"}),
    "blocked": frozenset({"doing"}),
    "review": frozenset({"doing"}),
}
AGENT_TOPIC_STATUSES = frozenset({"open", "waiting_on_user"})
NOTE_LIMIT = 240
PROPOSED_LABEL = "proposed"
ARCHIVED_LABEL = "archived"

WRITE_LIMITS = ((60.0, 30), (3600.0, 300))
PROPOSE_LIMITS = ((3600.0, 5),)
KEEP_SECONDS = 3600.0

_WINDOWS_PATH = re.compile(r"(?<![\w/\\])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|]*")
_POSIX_PATH = re.compile(r"(?<![\w:/.~])/(?:[^\s/\"'<>|]+/)*[^\s/\"'<>|]*")
_HOME_PATH = re.compile(r"(?<![\w/])~[\\/][^\s\"'<>|]*")


def check_agent(agent: object) -> str:
    """The agent id, or ``not_agent``. Daniel uses ``Registry``; ``user`` is the chat author."""
    if not isinstance(agent, str) or agent == PERSON or not valid_assignee(agent):
        raise EventRejected("not_agent")
    return agent


def may_touch(card: Mapping, agent: str, members: Collection[str]) -> bool:
    """Decision D: assigned to ``agent``, or unassigned in a topic that lists ``agent``."""
    assignee = card.get("assignee")
    if assignee is not None:
        return assignee == agent
    return card.get("topic") is not None and agent in members


def check_propose(may_create: bool, topic: object, room_topics: Collection[str]) -> None:
    """Decision C with ORCH.ROOM: off unless switched on, but an open orchestrator room opens its own topic."""
    if not may_create and topic not in room_topics:
        raise EventRejected("switched_off")


def check_owner(card: Mapping, agent: str, members: Collection[str]) -> None:
    if not may_touch(card, agent, members):
        raise EventRejected("not_owner")


def check_move(old: str, new: str) -> None:
    """Decision B: agents never reach ``done``; only the table's moves."""
    if new not in AGENT_MOVES.get(old, frozenset()):
        raise EventRejected("not_allowed")


def check_topic_status(old: str, new: str) -> None:
    """Decision F: ``open`` <-> ``waiting_on_user`` only. A ``done`` topic stays done."""
    if new not in AGENT_TOPIC_STATUSES or old not in AGENT_TOPIC_STATUSES:
        raise EventRejected("not_allowed")


def check_progress(value: object) -> int:
    """Decision E: an int 0-100. Going down is allowed (rework)."""
    if type(value) is not int or not 0 <= value <= 100:
        raise EventRejected("schema")
    return value


def _hashed(match: re.Match) -> str:
    text = match.group(0).rstrip(".,;:)]}")
    tail = match.group(0)[len(text):]
    if text in ("/", "\\\\") or len(text) < 2:
        return match.group(0)
    return "@external/" + hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:8] + tail


def scrub_paths(text: str) -> str:
    """Decision K for agent text: absolute and home paths become ``@external/<8 hex>`` (SHA-1)."""
    for pattern in (_WINDOWS_PATH, _HOME_PATH, _POSIX_PATH):
        text = pattern.sub(_hashed, text)
    return text


def clean_note(value: object) -> str:
    """An agent's note: sanitised, paths hashed, at most 240. ``None`` is empty."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EventRejected("schema")
    return sanitize_text(scrub_paths(sanitize_text(value, 4 * NOTE_LIMIT)), NOTE_LIMIT)


def allow(stamps: Sequence[float], now: float, limits: Sequence[tuple[float, int]]) -> tuple[bool, list[float]]:
    """Sliding windows over one actor's past writes. Returns (allowed, stamps to keep, now included if allowed)."""
    horizon = max(window for window, _ in limits)
    kept = sorted(s for s in stamps if isinstance(s, (int, float)) and 0 <= now - s <= horizon)
    for window, cap in limits:
        if sum(1 for s in kept if now - s < window) >= cap:
            return False, kept
    return True, kept + [now]
