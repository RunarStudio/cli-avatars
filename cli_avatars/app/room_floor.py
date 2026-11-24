"""MOVE.1: room floors, doors and routes in tile units, and the wander inside one room. No Tk.

A room's walls stand on its back tile row (``v0``) and column (``u0``); its front edges touch
the next room's walls. The floor an avatar may stand on is the room minus that row and column,
inset by ``MARGIN``. A door or arch piece on a back wall opens one tile of it; when the tile
beyond is another room's floor, the two rooms are linked there. Rooms are convex, so a straight
step between two points of one floor never meets a wall.
"""

from __future__ import annotations

import math
import zlib
from collections import deque
from dataclasses import dataclass

ROOM_NAMES = ("Hall", "Pantry", "Pit", "Atelier")
MARGIN = 0.35
LEG_S = 10.0
PAUSE = 0.5
TILE_W, TILE_H = 16, 8
_OPENINGS = ("b13-", "b14-", "b15-", "b16-")


@dataclass(frozen=True)
class Floor:
    name: str
    u0: int
    v0: int
    w: int
    h: int

    def box(self) -> tuple[float, float, float, float]:
        return (self.u0 + 1 + MARGIN, self.v0 + 1 + MARGIN, self.u0 + self.w - MARGIN, self.v0 + self.h - MARGIN)

    def holds(self, u: float, v: float) -> bool:
        a, b, c, d = self.box()
        return a - 1e-9 <= u <= c + 1e-9 and b - 1e-9 <= v <= d + 1e-9

    def covers(self, u: float, v: float) -> bool:
        return self.u0 <= u < self.u0 + self.w and self.v0 <= v < self.v0 + self.h

    def clamp(self, u: float, v: float) -> tuple[float, float]:
        a, b, c, d = self.box()
        return (min(max(u, a), c), min(max(v, b), d))

    def centre(self) -> tuple[float, float]:
        a, b, c, d = self.box()
        return ((a + c) / 2.0, (b + d) / 2.0)


@dataclass(frozen=True)
class Door:
    """One open wall tile between room ``a`` (the wall's owner) and room ``b``; ``path`` runs a to b."""

    a: str
    b: str
    rect: tuple[float, float, float, float]
    path: tuple[tuple[float, float], ...]


class Plan:
    def __init__(self, floors: list[Floor], doors: list[Door]) -> None:
        self.floors = floors
        self.doors = doors
        self._by_name = {f.name: f for f in floors}

    @classmethod
    def from_layout(cls, layout: dict | None) -> "Plan":
        floors, kept = [], []
        rooms = [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict)]
        for index, room in enumerate(rooms):
            origin, size = room.get("origin"), room.get("size")
            if not (_pair(origin) and _pair(size)) or room.get("floor", 0) != 0:
                continue
            name = room.get("name") if isinstance(room.get("name"), str) else None
            name = name or (ROOM_NAMES[index] if index < len(ROOM_NAMES) else f"Room {index + 1}")
            floors.append(Floor(name, origin[0], origin[1], size[0], size[1]))
            kept.append(room)
        plan = cls(floors, [])
        for room, floor in zip(kept, floors, strict=True):
            for cell in _opening_cells(room):
                door = plan._door(floor, cell)
                if door is not None:
                    plan.doors.append(door)
        return plan

    def names(self) -> list[str]:
        return [f.name for f in self.floors]

    def floor(self, name: str) -> Floor | None:
        return self._by_name.get(name)

    def room_at(self, u: float, v: float) -> str | None:
        """The room whose floor holds the point, else the room whose tiles cover it."""
        for floor in self.floors:
            if floor.holds(u, v):
                return floor.name
        for floor in self.floors:
            if floor.covers(u, v):
                return floor.name
        return None

    def walkable(self, u: float, v: float) -> bool:
        if any(f.holds(u, v) for f in self.floors):
            return True
        return any(d.rect[0] <= u <= d.rect[2] and d.rect[1] <= v <= d.rect[3] for d in self.doors)

    def route(self, start: tuple[float, float], room: str, goal: tuple[float, float]) -> list[tuple[float, float]]:
        """Waypoints from ``start`` to ``goal`` in ``room`` through the doors; a straight line when unlinked."""
        here = self.room_at(*start)
        path = [tuple(start)]
        if here is not None and not self._by_name[here].holds(*start):
            path.append(self._by_name[here].clamp(*start))
        for door, forward in self._hops(here, room):
            path.extend(door.path if forward else reversed(door.path))
        path.append(tuple(goal))
        return path

    def _hops(self, start: str | None, goal: str) -> list[tuple[Door, bool]]:
        if start is None or start == goal:
            return []
        seen = {start: []}
        queue = deque([start])
        while queue:
            here = queue.popleft()
            for door in self.doors:
                for there, forward in ((door.b, True), (door.a, False)) if here in (door.a, door.b) else ():
                    if there == here or there in seen:
                        continue
                    seen[there] = seen[here] + [(door, forward)]
                    if there == goal:
                        return seen[there]
                    queue.append(there)
        return []

    def _door(self, floor: Floor, cell: tuple[int, int]) -> Door | None:
        cu, cv = floor.u0 + cell[0], floor.v0 + cell[1]
        if cell[1] == 0 and cell[0] > 0:
            outer = next((f for f in self.floors if f is not floor and f.covers(cu + 0.5, cv - 0.5)), None)
            if outer is None:
                return None
            mid = cu + 0.5
            rect = (cu + 0.1, cv - MARGIN, cu + 0.9, cv + 1 + MARGIN)
            return Door(floor.name, outer.name, rect, ((mid, cv + 1 + MARGIN), (mid, cv + 0.5), (mid, cv - MARGIN)))
        if cell[0] == 0 and cell[1] > 0:
            outer = next((f for f in self.floors if f is not floor and f.covers(cu - 0.5, cv + 0.5)), None)
            if outer is None:
                return None
            mid = cv + 0.5
            rect = (cu - MARGIN, cv + 0.1, cu + 1 + MARGIN, cv + 0.9)
            return Door(floor.name, outer.name, rect, ((cu + 1 + MARGIN, mid), (cu + 0.5, mid), (cu - MARGIN, mid)))
        return None


def _pair(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(type(n) is int for n in value)


def _opening_cells(room: dict) -> list[tuple[int, int]]:
    items = list(room.get("structure") or [])
    if isinstance(room.get("door"), dict):
        items.append(room["door"])
    cells = []
    for item in items:
        name = item.get("piece") if isinstance(item, dict) else None
        if isinstance(name, str) and name.startswith(_OPENINGS) and _pair(item.get("at")):
            cells.append(tuple(item["at"]))
    return sorted(set(cells))


def px(p: tuple[float, float], q: tuple[float, float]) -> float:
    """Screen distance between two tile points at 1x."""
    du, dv = q[0] - p[0], q[1] - p[1]
    return math.hypot((du - dv) * TILE_W, (du + dv) * TILE_H)


def length(path) -> float:
    return sum(px(p, q) for p, q in zip(path, path[1:], strict=False))


def facing(p: tuple[float, float], q: tuple[float, float], last: int = 1) -> int:
    dx = (q[0] - q[1]) - (p[0] - p[1])
    return last if abs(dx) < 1e-9 else (1 if dx > 0 else -1)


def along(path, t: float) -> tuple[tuple[float, float], int]:
    """Point at fraction ``t`` of the path's screen length, and the facing there."""
    total = length(path)
    if total <= 0.0 or len(path) < 2:
        return tuple(path[-1]), 1
    left = min(1.0, max(0.0, t)) * total
    for p, q in zip(path, path[1:], strict=False):
        step = px(p, q)
        if left <= step and step > 0.0:
            k = left / step
            return (p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k), facing(p, q)
        left -= step
    return tuple(path[-1]), facing(path[-2], path[-1])


def _spot(floor: Floor, key: str, leg: int) -> tuple[float, float]:
    h = zlib.crc32(f"{key}:{leg}".encode("utf-8"))
    a, b, c, d = floor.box()
    return (a + (c - a) * (h & 0xFFFF) / 0xFFFF, b + (d - b) * (h >> 16) / 0xFFFF)


def wander(floor: Floor, key: str, now: float) -> tuple[tuple[float, float], int]:
    """Stand, then walk to the next spot of the room, one leg every ``LEG_S``; point and facing."""
    s = now / LEG_S + zlib.crc32(key.encode("utf-8")) / 2**32
    leg = math.floor(s)
    f = s - leg
    here = _spot(floor, key, leg)
    if f < PAUSE:
        return here, facing(_spot(floor, key, leg - 1), here)
    nxt = _spot(floor, key, leg + 1)
    k = (f - PAUSE) / (1.0 - PAUSE)
    return (here[0] + (nxt[0] - here[0]) * k, here[1] + (nxt[1] - here[1]) * k), facing(here, nxt)
