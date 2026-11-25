"""YOU-AVATAR: which avatars need Daniel, from the needs-you rows and the hook state. No Tk (docs/you-avatar.md).

A row reaches an avatar by its own link first: a decision's asker, a blocked card's assignee. Else the members of
the row's topic, else every agent of the topic's project (the room id is the project slug when the topic has none).
An agent whose hook state is ``blocked`` waits on a reply; ``error`` or a failed turn is a run that ended badly.
Bots and subagents never get a bubble. The most urgent row wins: decision, blocked, reply, run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

KINDS = ("decision", "blocked", "reply", "run")
GLYPHS = {"decision": "?", "blocked": "!", "reply": "?", "run": "!"}
COLOURS = {"decision": "#ffcf4a", "blocked": "#e0566a", "reply": "#7aa8ff", "run": "#6ad08a"}
WORDS = {"decision": "decision", "blocked": "blocked", "reply": "reply", "run": "run ended"}
FAILED = ("Run failed", "Run timed out")


@dataclass(frozen=True)
class Need:
    kind: str
    item: dict | None = None

    @property
    def stuck(self) -> bool:
        """BODY: a blocked card or a failed run slumps; the rest wait at the door."""
        if self.kind == "blocked":
            return True
        return self.kind == "run" and (self.item is None or self.item.get("detail") in FAILED)


def asker(sender: object) -> str | None:
    """A decision's ``from`` as an avatar id: Claude avatars keep the raw session id (``decide_watch``)."""
    if not isinstance(sender, str) or not sender:
        return None
    source, sep, rest = sender.partition(":")
    return rest if sep and source == "claude" else sender


def who(items: Iterable, topics: Iterable, cards: Iterable, agents: Mapping,
        askers: Mapping[str, str] | None = None) -> dict[str, Need]:
    """Top-level agent id to the most urgent thing it waits on Daniel for."""
    present = {aid: a for aid, a in agents.items()
               if not getattr(a, "parent_id", None) and getattr(a, "source", "") != "bot"}
    rooms = {t["id"]: t for t in topics if isinstance(t, dict) and isinstance(t.get("id"), str)}
    by_card = {c.get("id"): c for c in cards if isinstance(c, dict)}
    askers = askers or {}
    out: dict[str, Need] = {}

    def of_room(room) -> list[str]:
        topic = rooms.get(room) or {}
        members = [m for m in topic.get("members") or [] if m in present]
        if members:
            return members
        project = topic.get("project") or room
        return sorted(aid for aid, a in present.items() if project and getattr(a, "project", "") == project)

    for item in items:
        kind = item.get("kind") if isinstance(item, dict) else None
        if kind not in KINDS:
            continue
        sent: list[str] = []
        if kind == "decision":
            found = asker(askers.get(str(item.get("key", "")).partition(":")[2]))
            sent = [found] if found in present else []
        elif kind == "blocked":
            card = by_card.get(item.get("card")) or {}
            found = str(card.get("assignee") or "").partition("@")[0]
            sent = [found] if found in present else []
        for aid in sent or of_room(item.get("room")):
            out.setdefault(aid, Need(kind, item))
    for aid, agent in sorted(present.items()):
        status = getattr(agent, "status", "")
        if status == "blocked":
            out.setdefault(aid, Need("reply"))
        elif status == "error" or getattr(agent, "failed", False):
            out.setdefault(aid, Need("run"))
    return out


def near(feet: tuple[float, float] | None, spots: Mapping[str, tuple[float, float]], needs: Mapping[str, Need],
         reach: float) -> str | None:
    """The needing agent closest to ``feet`` within ``reach`` tiles, else None."""
    if feet is None:
        return None
    best, gap = None, reach
    for aid in needs:
        spot = spots.get(aid)
        if spot is None:
            continue
        d = ((spot[0] - feet[0]) ** 2 + (spot[1] - feet[1]) ** 2) ** 0.5
        if d <= gap:
            best, gap = aid, d
    return best
