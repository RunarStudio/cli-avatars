"""ROOMS.1: place a new room on the nearest free spot off a room's connection point. No Tk.

Rooms and corridors are tile rectangles ``(u0, v0, w, h)``: walls on the back row ``v0`` and column
``u0``, the front edges open. A corridor is 3 tiles across (a wall and two floor tiles), as the
START.1 session corridors are. Two rectangles that touch along the way are joined by a door on the
back wall of the one further along ``u`` (or ``v``); it opens onto the other's floor. Doors that line
up give one straight corridor; offset ones a jog of three pieces. Longer than ``MAX_CORRIDOR``
tiles, or crossing a taken rectangle: that spot does not fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CORRIDOR = 12
MIN_RUN = 3
WIDE = 3
_POINT = re.compile(r"^([nesw])(\d{1,2})$")
# side -> (axis the corridor runs along: 0 = u, 1 = v; +1 away from the origin, -1 towards it)
SIDES = {"n": (1, -1), "s": (1, 1), "e": (0, 1), "w": (0, -1)}

Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class Placement:
    room: Rect
    corridors: tuple[Rect, ...]
    doors: tuple[tuple[int, tuple[int, int]], ...]
    length: int

    def rects(self, anchor: Rect) -> list[Rect]:
        """The chain in order: anchor, corridors, room; ``doors`` index into it."""
        return [anchor, *self.corridors, self.room]


def overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def parse_point(rect: Rect, point: object) -> tuple[str, int] | None:
    """``("e", v)``: the side and the across tile a corridor's first floor row starts on."""
    match = _POINT.match(point) if isinstance(point, str) else None
    if match is None:
        return None
    side, index = match.group(1), int(match.group(2))
    axis, _sign = SIDES[side]
    lo, length = (rect[0], rect[2]) if axis == 1 else (rect[1], rect[3])
    return (side, lo + index) if 1 <= index <= length - 1 else None


def points(rect: Rect) -> list[str]:
    """Three points per side: both ends and the middle."""
    out = []
    for side in ("n", "e", "s", "w"):
        length = rect[2] if SIDES[side][0] == 1 else rect[3]
        for index in sorted({1, length // 2, length - 1}):
            out.append(f"{side}{index}")
    return out


def _mk(axis: int, along: int, along_len: int, across: int, across_len: int) -> Rect:
    return (along, across, along_len, across_len) if axis == 0 else (across, along, across_len, along_len)


def _chain(anchor: Rect, side: str, pieces) -> list[Rect]:
    """Rectangles laid one after another off ``side``: ``(along_len, across_lo, across_len)`` each."""
    axis, sign = SIDES[side]
    lo, length = (anchor[0], anchor[2]) if axis == 0 else (anchor[1], anchor[3])
    at = lo + length if sign > 0 else lo
    out = []
    for along_len, across, across_len in pieces:
        if sign > 0:
            out.append(_mk(axis, at, along_len, across, across_len))
            at += along_len
        else:
            at -= along_len
            out.append(_mk(axis, at, along_len, across, across_len))
    return out


def _door(axis: int, owner: Rect, x: int) -> tuple[int, int]:
    return (0, x - owner[1]) if axis == 0 else (x - owner[0], 0)


def _build(anchor: Rect, side: str, pieces, crossings: list[int]) -> tuple[list[Rect], list]:
    """The chain and its doors: each junction's door sits on the back wall of the rectangle further along."""
    axis, sign = SIDES[side]
    rects = [anchor, *_chain(anchor, side, pieces)]
    doors = []
    for i, x in enumerate(crossings):
        owner = i + 1 if sign > 0 else i
        doors.append((owner, _door(axis, rects[owner], x)))
    return rects, doors


def _candidates(c: int, size: tuple[int, int], axis: int):
    """``(cost, pieces, crossings)`` for every straight and jog spot, cheapest first."""
    room_along, room_across = (size[0], size[1]) if axis == 0 else (size[1], size[0])
    found = []
    for run in range(MIN_RUN, MAX_CORRIDOR + 1):
        for b0 in range(c - room_across + 1, c):
            shift = abs(b0 - (c - room_across // 2))
            found.append(((run, 0, shift), [(run, c - 1, WIDE), (room_along, b0, room_across)], [c, c]))
    runs = [0, *range(MIN_RUN, MAX_CORRIDOR + 1)]
    for first in runs:
        for last in runs:
            for c2 in range(c - MAX_CORRIDOR, c + MAX_CORRIDOR + 1):
                length = first + WIDE + last + abs(c2 - c)
                if c2 == c or length > MAX_CORRIDOR:
                    continue
                pieces = [(first, c - 1, WIDE)] if first else []
                pieces.append((WIDE, min(c, c2) - 1, abs(c2 - c) + WIDE))
                if last:
                    pieces.append((last, c2 - 1, WIDE))
                pieces.append((room_along, c2 - room_across // 2, room_across))
                found.append(((length, 1, abs(c2 - c)), pieces, [c] * (1 + bool(first)) + [c2] * (1 + bool(last))))
    found.sort(key=lambda row: row[0])
    return found


def place(anchor: Rect, point: str, size: tuple[int, int], taken: list[Rect]) -> Placement | None:
    """The cheapest spot for a ``size`` room off ``point`` of ``anchor`` that crosses nothing in ``taken``."""
    parsed = parse_point(anchor, point)
    if parsed is None or not all(isinstance(n, int) and 0 < n <= 32 for n in size):
        return None
    side, c = parsed
    axis = SIDES[side][0]
    for (length, _jog, _shift), pieces, crossings in _candidates(c, size, axis):
        if length > MAX_CORRIDOR:
            continue
        rects, doors = _build(anchor, side, pieces, crossings)
        if any(overlaps(r, t) for r in rects[1:] for t in taken):
            continue
        return Placement(rects[-1], tuple(rects[1:-1]), tuple(doors), length)
    return None
