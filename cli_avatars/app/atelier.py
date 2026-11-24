"""ATELIER.1: the guest helper's backroom beside the throne room, and the walk to it.

A bot needs the guest while one of its cards is ``blocked`` and labelled ``guest``.
Its avatar walks from its hall spot through the right-wall door to the atelier desk,
waits there with the amber mark, and walks back when the card clears. The guest is a
helper, not the user. Numbers follow ``docs/img/atelier-preview.png``. No Tk here.
"""

from __future__ import annotations

import math
from dataclasses import replace

from cli_avatars.app import throne_model as tm
from cli_avatars.app.needs_walk import Walker, beside, needing

GUEST_ID = "__guest__"
GUEST_SKIN = "frost_wanderer"
GUEST_NAME = "GUEST"
GUEST_COLOR = "#bcd4f0"
ROOM = (15, -6, 6, 7)
LANDING = (11, -2, 4, 2)
DESK = (17.3, -4.3)
GUEST_SPOT = (17.75, -5.15)
DESK_SPOT = (17.9, -2.9)
SPOT_GAP = 0.9
MAX_SPOTS = 5
LANE_U = tm.DOOR_U + 0.3
LANE_V = -1.5
HALL_V = 0.6
WAYPOINTS = ((14.9, LANE_V), (16.1, -2.1))
WALK_SPEED = 40.0


def needing_guest(topics, cards, agents) -> set[str]:
    """Top-level agent ids whose blocked ``guest`` card needs the guest helper."""
    return set(needing(topics, cards, agents, guest=True))


def desk_spot(index: int) -> tuple[float, float]:
    """Waiting spot ``index``: at the desk, then right and left of it. Extra bots share the last one."""
    index = min(index, MAX_SPOTS - 1)
    return DESK_SPOT if index == 0 else beside(DESK_SPOT, index - 1, SPOT_GAP)


def route(home: tuple[float, float], spot: tuple[float, float]) -> list[tuple[float, float]]:
    """Hall spot to the door lane, through the door, across the landing, to the desk spot."""
    return [home, (LANE_U, max(home[1], HALL_V)), (LANE_U, LANE_V), *WAYPOINTS, spot]


def _px(p, q) -> float:
    du, dv = q[0] - p[0], q[1] - p[1]
    return math.hypot((du - dv) * tm.TILE, (du + dv) * tm.TILE / 2)


def length(path) -> float:
    """Screen length of ``path`` at 1x, in pixels."""
    return sum(_px(p, q) for p, q in zip(path, path[1:], strict=False))


def along(path, t: float) -> tuple[float, float]:
    """Point at fraction ``t`` of the path's screen length."""
    if t >= 1.0:
        return path[-1]
    left = max(0.0, t) * length(path)
    for p, q in zip(path, path[1:], strict=False):
        step = _px(p, q)
        if step and left <= step:
            k = left / step
            return (p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k)
        left -= step
    return path[-1]


class Errands:
    """Moves hall agents that need the guest to the atelier and back. The orchestrator stays seated."""

    def __init__(self, speed: float = WALK_SPEED) -> None:
        self.walker = Walker(speed=speed)

    def step(self, seating: tm.Seating, need, now: float) -> tuple[tm.Seating, frozenset]:
        """``seating`` with walkers moved along their routes, and the ids that wear the mark."""
        homes = {p.actor.id: (p.u, p.v) for n, p in enumerate(seating.placed) if p.main and n > 0}
        need = set(need) & set(homes)
        order = sorted(need | (self.walker.walking() & set(homes)))
        routes = {aid: route(homes[aid], desk_spot(i)) for i, aid in enumerate(order)}
        self.walker.step(need, {aid: length(path) for aid, path in routes.items()}, now)
        placed = []
        for p in seating.placed:
            t = self.walker.progress(p.actor.id)
            if p.actor.id in routes and t is not None:
                u, v = along(routes[p.actor.id], t)
                p = replace(p, u=u, v=v)
            placed.append(p)
        marked = frozenset(aid for aid in order if self.walker.marked(aid))
        return replace(seating, placed=tuple(placed)), marked

    def arrived(self, aid: str) -> bool:
        return self.walker.arrived(aid)

    def moving(self) -> bool:
        """True while a bot is on its way there or back; a bot waiting at the desk is not moving."""
        w = self.walker
        return any(not (w.marked(aid) and w.arrived(aid)) for aid in w.walking())
