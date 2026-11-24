"""AV.1 needs-me walk: a room that needs the user sends its avatar to the user's side.

A room needs the user while one of its cards is ``blocked`` or its topic is
``waiting_on_user``. The avatar walks over, waits beside the user with the
amber mark, and walks back home when the state clears. A blocked card labelled
``guest`` needs the guest helper instead (ATELIER.1). No Tk here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cli_avatars.model.crossing import mix

BLOCKED = "blocked"
WAITING = "waiting_on_user"
GUEST_LABEL = "guest"
MAX_STEP_S = 0.25


def for_guest(card: Mapping) -> bool:
    labels = card.get("labels")
    return isinstance(labels, list) and GUEST_LABEL in labels


def needing(topics: Iterable, cards: Iterable, agents: Mapping, guest: bool = False) -> dict[str, str]:
    """Top-level agent id to the reason its room needs the user, or with ``guest`` the guest helper."""
    present = {aid for aid, agent in agents.items() if not getattr(agent, "parent_id", None)}
    rooms = {t["id"]: t for t in topics if isinstance(t, dict) and isinstance(t.get("id"), str)}
    out: dict[str, str] = {}

    def by_project(project) -> list[str]:
        if not project:
            return []
        return sorted(aid for aid in present if getattr(agents[aid], "project", "") == project)

    def members(topic) -> list[str]:
        found = topic.get("members") if isinstance(topic, dict) else None
        return [m for m in found or [] if m in present]

    for card in cards:
        if not isinstance(card, dict) or card.get("column") != BLOCKED or for_guest(card) != guest:
            continue
        who = str(card.get("assignee") or "").partition("@")[0]
        sent = [who] if who in present else members(rooms.get(card.get("topic")))
        for aid in sent or by_project(card.get("project")):
            out.setdefault(aid, BLOCKED)
    for topic in rooms.values():
        if guest or topic.get("status") != WAITING:
            continue
        for aid in members(topic) or by_project(topic.get("project")):
            out.setdefault(aid, WAITING)
    return out


def read_rooms(directory) -> tuple[list, list]:
    """Topics and blocked cards on every project board. Empty on any read error."""
    from events import EventRejected
    from registry.facade import Registry
    from topics import list_topics

    try:
        topics = list_topics(directory, timeout=0.05)
    except (EventRejected, OSError, ValueError):
        topics = []
    cards: list = []
    try:
        registry = Registry(directory)
        root = Path(registry.store.root)
        for project in sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
            try:
                cards.extend(registry.task_list(project, column=BLOCKED))
            except EventRejected:
                continue
    except (EventRejected, OSError, ValueError):
        cards = []
    return topics, cards


def beside(user: tuple[float, float], index: int, gap: float) -> tuple[float, float]:
    """Waiting spot ``index``: right of the user, then left, one ``gap`` further each pair."""
    side = 1 if index % 2 == 0 else -1
    return (user[0] + side * gap * (index // 2 + 1), user[1])


@dataclass
class Walker:
    """Walk progress per agent: 0 at home, 1 beside the user. ``speed`` is px per second."""

    speed: float
    _t: dict[str, float] = field(default_factory=dict)
    _need: set[str] = field(default_factory=set)
    _last: float | None = None

    def step(self, need: set[str], spans: Mapping[str, float], now: float) -> None:
        dt = 0.0 if self._last is None else min(MAX_STEP_S, max(0.0, now - self._last))
        self._last = now
        self._need = set(need)
        for aid in self._need | set(self._t):
            span = float(spans.get(aid, 0.0))
            move = 1.0 if span < 1.0 else dt * self.speed / span
            t = self._t.get(aid, 0.0) + (move if aid in self._need else -move)
            if aid not in self._need and t <= 0.0:
                self._t.pop(aid, None)
                continue
            self._t[aid] = min(1.0, max(0.0, t))

    def walking(self) -> set[str]:
        return set(self._t)

    def progress(self, aid: str) -> float | None:
        return self._t.get(aid)

    def arrived(self, aid: str) -> bool:
        return self._t.get(aid, 0.0) >= 1.0

    def marked(self, aid: str) -> bool:
        return aid in self._need

    def at(self, aid: str, home: tuple[float, float], goal: tuple[float, float]) -> tuple[float, float] | None:
        if aid not in self._t:
            return None
        return mix(home[0], home[1], goal[0], goal[1], self._t[aid])
