"""BODY: read an agent's state from its body (docs/body-language.md). No Tk, no AI, no git.

Flowing agents stride, stuck ones slump on a bench, one waiting on Daniel taps its foot at the room door, and a room
whose run has gone on past ``smoke_min`` smokes, thicker with time. Everything comes from what the app already
holds: hook states and their last activity, blocked cards, waiting topics, the needs-you list (open decisions,
replies, ended runs) and the start of each run, kept in memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cli_avatars.app.needs_walk import BLOCKED, WAITING, needing

STRIDE, SLUMP, TAP, IDLE = "stride", "slump", "tap", "idle"
WORDS = {STRIDE: "flowing", SLUMP: "stuck", TAP: "waiting", IDLE: "idle"}
STUCK, WAITS = BLOCKED, WAITING
WORKING = ("busy", "thinking", "subagent")
FAILED_RUNS = ("Run failed", "Run timed out")
WAIT_KINDS = ("decision", "reply", "run")
GAP_S = 90.0
EASE_S = 0.4
CONFIG_NAME = "config.json"


@dataclass(frozen=True)
class Thresholds:
    enabled: bool = True
    flow_s: float = 120.0
    smoke_s: float = 1200.0
    thick_s: float = 3600.0


def thresholds(config: object) -> Thresholds:
    """``config["body"]``: ``enabled``, ``flow_s``, ``smoke_min``, ``thick_min``; a bad value keeps its default."""
    section = config.get("body") if isinstance(config, dict) else None
    section = section if isinstance(section, dict) else {}
    base = Thresholds()

    def number(key: str, default: float, unit: float) -> float:
        value = section.get(key)
        ok = type(value) in (int, float) and value > 0
        return float(value) * unit if ok else default

    enabled = section.get("enabled")
    smoke_s = number("smoke_min", base.smoke_s, 60.0)
    thick_s = number("thick_min", base.thick_s, 60.0)
    return Thresholds(enabled if type(enabled) is bool else base.enabled, number("flow_s", base.flow_s, 1.0),
                      smoke_s, thick_s if thick_s > smoke_s else smoke_s + 60.0)


def thresholds_in(directory: Path | str) -> Thresholds:
    try:
        return thresholds(json.loads((Path(directory) / CONFIG_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Thresholds()


def flowing(agent, now: float, th: Thresholds) -> bool:
    return getattr(agent, "status", "") in WORKING and now - float(getattr(agent, "last_seen", 0.0)) <= th.flow_s


def pose_for(agent, reason: str | None, now: float, th: Thresholds) -> str:
    """Stuck (blocked card, error, failed turn) slumps; waiting on Daniel taps; recent work strides."""
    status = getattr(agent, "status", "")
    if reason == STUCK or status == "error" or getattr(agent, "failed", False):
        return SLUMP
    if reason == WAITS or status == "blocked":
        return TAP
    return STRIDE if flowing(agent, now, th) else IDLE


def reasons(topics: Iterable, cards: Iterable, items: Iterable, agents: Mapping) -> dict[str, str]:
    """Agent id to ``STUCK`` or ``WAITS`` from blocked cards, waiting topics and needs-you rows."""
    topics = [t for t in topics if isinstance(t, dict) and isinstance(t.get("id"), str)]
    known = {t["id"]: t for t in topics}
    cards = [c for c in cards if isinstance(c, dict)]
    waits, stuck = [], []
    for item in items:
        room = item.get("room") if isinstance(item, dict) else None
        if not isinstance(room, str) or item.get("kind") not in WAIT_KINDS:
            continue
        base = known.get(room) or {"id": room}
        if item["kind"] == "run" and item.get("detail") in FAILED_RUNS:
            stuck.append({"column": BLOCKED, "topic": room, "project": base.get("project")})
        else:
            waits.append({**base, "status": WAITING})
    return needing(topics + waits, cards + stuck, agents)


def smoke(start: float | None, now: float, th: Thresholds) -> float:
    """0 until a run passes ``smoke_s``; then 0.2 rising to 1.0 at ``thick_s``."""
    if start is None or now - start < th.smoke_s:
        return 0.0
    k = (now - start - th.smoke_s) / max(1.0, th.thick_s - th.smoke_s)
    return round(min(1.0, 0.2 + 0.8 * k), 3)


def room_smoke(starts: Mapping, rooms: Mapping, now: float, th: Thresholds) -> dict[str, float]:
    """Each room's smoke from the longest run among the avatars in it; rooms without smoke are left out."""
    out: dict[str, float] = {}
    for aid, start in starts.items():
        room, level = rooms.get(aid), smoke(start, now, th)
        if room and level > 0.0:
            out[room] = max(out.get(room, 0.0), level)
    return out


@dataclass
class Runs:
    """When each agent's current run began: work starts one, a pause longer than ``gap_s`` ends it."""

    gap_s: float = GAP_S
    _start: dict[str, float] = field(default_factory=dict)
    _quiet: dict[str, float] = field(default_factory=dict)

    def see(self, aid: str, working: bool, now: float) -> float | None:
        if working:
            self._quiet.pop(aid, None)
            return self._start.setdefault(aid, now)
        if aid not in self._start:
            return None
        quiet = self._quiet.setdefault(aid, now)
        if now - quiet > self.gap_s:
            self._start.pop(aid, None)
            self._quiet.pop(aid, None)
            return None
        return self._start[aid]

    def start(self, aid: str) -> float | None:
        return self._start.get(aid)

    def keep(self, ids: set[str]) -> None:
        for aid in [a for a in self._start if a not in ids]:
            self._start.pop(aid, None)
            self._quiet.pop(aid, None)


@dataclass
class Shift:
    """Eased pose changes: ``see`` gives the pose, the one before and the blend 0..1 (ease-out)."""

    ease_s: float = EASE_S
    _now: dict[str, tuple[str, str, float]] = field(default_factory=dict)
    _changes: list[tuple[str, str, str]] = field(default_factory=list)

    def see(self, aid: str, pose: str, now: float) -> tuple[str, str, float]:
        have = self._now.get(aid)
        if have is None:
            self._now[aid] = (pose, pose, now - self.ease_s)
        elif have[0] != pose:
            self._changes.append((aid, have[0], pose))
            self._now[aid] = (pose, have[0], now)
        pose, was, since = self._now[aid]
        t = min(1.0, max(0.0, (now - since) / self.ease_s))
        return pose, was, 1.0 - (1.0 - t) ** 3

    def changed(self) -> list[tuple[str, str, str]]:
        out, self._changes = self._changes, []
        return out

    def keep(self, ids: set[str]) -> None:
        for aid in [a for a in self._now if a not in ids]:
            self._now.pop(aid)


@dataclass(frozen=True)
class Found:
    poses: dict[str, str]
    smoke: dict[str, float]

    def word(self, aid: str) -> str:
        return WORDS[self.poses.get(aid, IDLE)]


def states(agents: Mapping, topics: Iterable, cards: Iterable, items: Iterable, rooms: Mapping, runs: Runs,
           now: float, th: Thresholds) -> Found:
    """Every top-level agent's pose and each room's smoke; nothing while ``body.enabled`` is false."""
    if not th.enabled:
        return Found({}, {})
    top = {aid: a for aid, a in agents.items() if not getattr(a, "parent_id", None)}
    why = reasons(topics, cards, items, top)
    poses = {aid: pose_for(agent, why.get(aid), now, th) for aid, agent in top.items()}
    starts = {aid: runs.see(aid, flowing(agent, now, th), now) for aid, agent in top.items()}
    runs.keep(set(top))
    return Found(poses, room_smoke(starts, rooms, now, th))
