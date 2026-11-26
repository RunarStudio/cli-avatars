"""BOSS-ROOM.1: the Oni Pit and the Crypt, two rooms that grow with the backlog (docs/backlog-boss.md). No Tk.

The Oni Pit's size follows the boss HP: HP 0 is the smallest bare room, then one size step per oni stage. The Crypt
holds one skull per forgotten card (open with no update for ``FORGOTTEN_DAYS``, or archived while not done) and
steps up with the skull count. Each room keeps a footprint at its largest size, placed by ``room_place`` after the
session slots, your rooms and the park's spot: the pit off the Apothecary, the Crypt off the pit's corridor (next
door). A room of any size sits inside its footprint with its door wall fixed and grows away from the door, so a
resize never meets another room. ``Grow`` moves the shown size one tile a step toward the backlog's.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from cli_avatars.app import park
from cli_avatars.app import room_place as rp
from cli_avatars.app.custom_rooms import APOTHECARY_RECT
from cli_avatars.app.room_skins import dress

FORGOTTEN_DAYS = 30
PIT, CRYPT = "Oni Pit", "Crypt"
PIT_KIND, CRYPT_KIND = "oni-pit", "crypt"
# (from HP or skull count, (w, h) in tiles): HP 0 and no skulls are the smallest, bare room
PIT_STEPS = ((0, (4, 4)), (1, (6, 5)), (6, (8, 6)), (16, (10, 8)), (31, (12, 10)))
CRYPT_STEPS = ((0, (4, 4)), (1, (5, 5)), (9, (7, 6)), (17, (9, 7)), (31, (11, 8)))
PIT_POINTS = ("w7", "s1", "s9", "e7", "w4", "s5", "e4", "w1", "e1", "n1", "n5", "n9")
PIT_SKIN, CRYPT_SKIN = "wardens-hold", "ossuary"
GROW_S = 0.12
READ_S = 2.0
TITLE_LIMIT = 80
_OPEN = ("todo", "doing", "review", "blocked")
NICHE_ROWS = (3, 14)
FACE = 0.3
HEAP = ((0.0, 0.0), (-1.4, 0.9), (1.2, -0.8))
HEAP_ROWS = (6, 5, 4, 3, 2, 1)
_WALL_BUSY = ("b13-", "b14-", "b15-", "b16-", "b21-", "b22-", "b23-", "b24-")


def _size(steps, n: int) -> tuple[int, int]:
    return [size for edge, size in steps if n >= edge][-1]


def pit_size(hp: int) -> tuple[int, int]:
    return _size(PIT_STEPS, hp)


def crypt_size(skulls: int) -> tuple[int, int]:
    return _size(CRYPT_STEPS, skulls)


def forgotten(cards: Iterable, now: float) -> list[dict]:
    """One skull per forgotten card, deduped by id, longest forgotten first."""
    from backlog_boss import _age_days

    found: dict[str, dict] = {}
    for card in cards:
        if not isinstance(card, Mapping) or not isinstance(card.get("id"), str) or card.get("column") == "done":
            continue
        archived = "archived" in (card.get("labels") or [])
        days = _age_days(card, now)
        if card["id"] in found or not (archived or (card.get("column") in _OPEN and days >= FORGOTTEN_DAYS)):
            continue
        found[card["id"]] = {"id": card["id"], "title": str(card.get("title") or "")[:TITLE_LIMIT],
                             "topic": card.get("topic") or "", "why": "archived" if archived else "stale",
                             "days": int(days)}
    return sorted(found.values(), key=lambda r: (-r["days"], r["id"]))


def slots(before: Mapping[str, int], ids: Iterable[str]) -> dict[str, int]:
    """Skull id -> niche index: a skull keeps its niche, a new one takes the lowest free niche."""
    ids = list(dict.fromkeys(ids))
    out = {i: before[i] for i in ids if i in before}
    used = set(out.values())
    free = (n for n in range(len(ids) + len(used) + 1) if n not in used)
    for i in ids:
        if i not in out:
            out[i] = next(free)
    return out


def niches(room: dict | None) -> list[tuple[float, float, str, int]]:
    """``(u, v, side, lift px)`` per niche of the Crypt ``room``: on each back-wall tile without a door or a torch,
    the lower row first."""
    if not room:
        return []
    (u0, v0), (w, h) = room["origin"], room["size"]
    busy = {tuple(i["at"]) for i in room.get("structure") or [] if str(i.get("piece", "")).startswith(_WALL_BUSY)}
    walls = [(u0 + x + 0.5, v0 + FACE, "r", (x, 0)) for x in range(1, w - 1)]
    walls += [(u0 + FACE, v0 + y + 0.5, "l", (0, y)) for y in range(1, h - 1)]
    walls = [(u, v, side) for u, v, side, cell in walls if cell not in busy]
    return [(u, v, side, lift) for lift in NICHE_ROWS for u, v, side in walls]


def heap(room: dict | None, n: int) -> list[tuple[float, float, int]]:
    """``(u, v, lift px)`` for ``n`` skulls piled on the floor, a pyramid at a time."""
    if not room or n <= 0:
        return []
    (u0, v0), (w, h) = room["origin"], room["size"]
    cu, cv = u0 + (w + 1) / 2.0, v0 + (h + 1) / 2.0
    out = []
    for du, dv in HEAP:
        for level, count in enumerate(HEAP_ROWS):
            for j in range(count):
                k = (j - (count - 1) / 2.0) * 0.36
                out.append((cu + du + k, dv + cv - k, level * 5))
    return out[:n]


# --- placement ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spot:
    """A room's footprint at its largest: ``found`` off ``point`` of ``anchor``."""

    anchor: rp.Rect
    point: str
    found: rp.Placement

    def rect(self, size: tuple[int, int]) -> rp.Rect:
        """The room at ``size`` inside the footprint: the wall at the door stays, it grows away from the door."""
        side, c = rp.parse_point(self.anchor, self.point)
        axis, sign = rp.SIDES[side]
        fu, fv, fw, fh = self.found.room
        f_along, f_len, f_across, f_wide = (fu, fw, fv, fh) if axis == 0 else (fv, fh, fu, fw)
        along_len, across_len = (min(size[0], fw), min(size[1], fh)) if axis == 0 else (min(size[1], fh),
                                                                                         min(size[0], fw))
        along = f_along if sign > 0 else f_along + f_len - along_len
        cross = self._door_across(axis)
        across = min(max(cross - across_len // 2, f_across), f_across + f_wide - across_len)
        return (along, across, along_len, across_len) if axis == 0 else (across, along, across_len, along_len)

    def entry(self, rect: rp.Rect) -> tuple[int, int]:
        """The room tile just inside its door, relative to ``rect``."""
        side, _c = rp.parse_point(self.anchor, self.point)
        axis, sign = rp.SIDES[side]
        across = self._door_across(axis) - (rect[1] if axis == 0 else rect[0])
        along = 1 if sign > 0 else (rect[2] if axis == 0 else rect[3]) - 1
        return (along, across) if axis == 0 else (across, along)

    def _door_across(self, axis: int) -> int:
        owner, (x, y) = self.found.doors[-1]
        rect = self.found.rects(self.anchor)[owner]
        return rect[1] + y if axis == 0 else rect[0] + x


def spots(taken: Iterable[rp.Rect]) -> tuple[Spot | None, Spot | None]:
    """The pit's and the Crypt's footprints; the first pit point where the Crypt fits next door wins."""
    taken = list(taken)
    first = None
    for point in PIT_POINTS:
        found = rp.place(APOTHECARY_RECT, point, pit_size(10 ** 6), taken)
        if found is None:
            continue
        pit = Spot(APOTHECARY_RECT, point, found)
        first = first or pit
        used = taken + [found.room, *found.corridors]
        for anchor in (*found.corridors, APOTHECARY_RECT):
            for q in rp.points(anchor):
                crypt = rp.place(anchor, q, crypt_size(10 ** 6), used)
                if crypt is not None:
                    return pit, Spot(anchor, q, crypt)
    return first, None


def footprints(taken: Iterable[rp.Rect]) -> list[rp.Rect]:
    return [r for s in spots(taken) if s is not None for r in (s.found.room, *s.found.corridors)]


def extend(layout: dict | None, taken, sizes) -> dict | None:
    """``layout`` with the Oni Pit and the Crypt at ``sizes`` ((w, h), (w, h)) and their corridors; the park's
    spot counts as taken (on or off), so the rooms never move when it is switched."""
    if layout is None or sizes is None:
        return layout
    taken = list(taken)
    taken += park.rects(park.extend({"rooms": []}, taken))
    pit, crypt = spots(taken)
    rooms = list(layout.get("rooms") or [])
    for spot, size, name, kind, skin in ((pit, sizes[0], PIT, PIT_KIND, PIT_SKIN),
                                         (crypt, sizes[1], CRYPT, CRYPT_KIND, CRYPT_SKIN)):
        if spot is not None:
            rooms = _add(rooms, spot, spot.rect(size), name, kind, skin)
    return dict(layout, rooms=rooms)


def _add(rooms: list[dict], spot: Spot, rect: rp.Rect, name: str, kind: str, skin: str) -> list[dict]:
    from cli_avatars.app.session_rooms import _corridor

    chain = [spot.anchor, *spot.found.corridors, rect]
    cells: dict[int, dict] = {}
    for owner, (x, y) in spot.found.doors:
        u, v = spot.found.rects(spot.anchor)[owner][0] + x, spot.found.rects(spot.anchor)[owner][1] + y
        cells.setdefault(owner, {})[(u - chain[owner][0], v - chain[owner][1])] = "arch"
    key = f"{kind}~{spot.point}"
    out = list(rooms)
    if cells.get(0):
        out = [_opened(r, spot.anchor, cells[0]) for r in out]
    for i, (u, v, w, h) in enumerate(spot.found.corridors):
        piece = _corridor(f"~{kind}-{i}", (u, v), (w, h), cells.get(i + 1, {}))
        torch = (w - 1, 0) if w >= h else (0, h - 1)
        if torch not in cells.get(i + 1, {}):
            piece["structure"].append({"piece": "b24-antorcha-der" if torch[1] == 0 else "b23-antorcha-izq",
                                       "at": list(torch)})
        piece.update(corridor=True, kind=kind, build=key)
        out.append(piece)
    u, v, w, h = rect
    door = {c: "skin" for c in cells.get(len(chain) - 1, {})}
    structure = dress(skin, w, h, door, props=False) + _props(kind, w, h, spot.entry(rect))
    out.append({"name": name, "origin": [u, v], "size": [w, h], "floor": 0, "kind": kind, "skin": skin,
                "build": key, "structure": structure})
    return out


def _opened(room: dict, rect: rp.Rect, cells: dict) -> dict:
    """The anchor room (or corridor) with an arch where the new corridor meets its back wall."""
    if list(room.get("origin") or []) != [rect[0], rect[1]] or list(room.get("size") or []) != [rect[2], rect[3]]:
        return room
    from cli_avatars.app.custom_rooms import _opened as opened

    return dict(room, structure=opened(room.get("structure") or [], cells))


def _props(kind: str, w: int, h: int, entry: tuple[int, int]) -> list[dict]:
    """Kit pieces: braziers and chains in the pit (more as it grows), a candle table, a register and bones in the
    Crypt (no prop skulls: every skull there is a card); the grate at the pit's heart shows while it is empty."""
    def free(x, y):
        return 0 < x < w and 0 < y < h and abs(x - entry[0]) + abs(y - entry[1]) > 1

    if kind == PIT_KIND:
        picks = [("b05-losa-rejilla", (w // 2, h // 2))] if (w, h) == PIT_STEPS[0][1] else []
        if w >= 6:
            picks += [("o20-brasero", (1, h - 1)), ("o20-brasero", (w - 1, 1))]
        if w >= 8:
            picks += [("o03-grilletes", (2, 1)), ("o03-grilletes", (1, 2))]
        if w >= 10:
            picks += [("o20-brasero", (w - 1, h - 1)), ("o07-huesos-cruzados", (w - 2, h - 2))]
    else:
        picks = [("o14-mesa-con-vela", (1, h - 1)), ("o10-atril-con-grimorio", (w - 1, 1))]
        if w >= 7:
            picks += [("o07-huesos-cruzados", (w - 2, h - 2))]
    return [{"piece": p, "at": list(at)} for p, at in picks if free(*at) or p.startswith("b05")]


def rects(layout: dict | None) -> list[rp.Rect]:
    """The pit's and the Crypt's rooms and corridors as drawn, for what is placed after them."""
    return [(r["origin"][0], r["origin"][1], r["size"][0], r["size"][1]) for r in (layout or {}).get("rooms") or []
            if isinstance(r, dict) and r.get("kind") in (PIT_KIND, CRYPT_KIND)]


def room(layout: dict | None, kind: str) -> dict | None:
    return next((r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("kind") == kind
                 and not r.get("corridor")), None)


# --- the live sizes ---------------------------------------------------------------------------------------------
class Grow:
    """The shown size: the first call shows the target, then one tile per ``GROW_S`` on each axis toward it."""

    def __init__(self) -> None:
        self.shown: tuple[int, int] | None = None
        self.at = 0.0

    def step(self, target: tuple[int, int], now: float) -> tuple[int, int]:
        if self.shown is None or now < self.at:
            self.shown, self.at = target, now
        elif self.shown != target and now - self.at >= GROW_S - 1e-6:
            w, h = self.shown
            self.shown = (w + (target[0] > w) - (target[0] < w), h + (target[1] > h) - (target[1] < h))
            self.at = now
        return self.shown


_READS: dict[str, tuple[float, int, list[dict]]] = {}


def remember(directory: Path | str, cards: Iterable, now: float) -> tuple[int, list[dict]]:
    """HP and the forgotten cards from ``cards`` read at ``now``; kept ``READ_S`` for the layout and the phone."""
    from backlog_boss import hp

    cards = list(cards)
    found = (hp(cards, now), forgotten(cards, now))
    _READS[str(directory)] = (time.monotonic(), *found)
    return found


def read(directory: Path | str, now: float) -> tuple[int, list[dict]]:
    """HP and the forgotten cards, read again at most every ``READ_S``."""
    from backlog_boss import cards_in

    held = _READS.get(str(directory))
    if held is not None and time.monotonic() - held[0] < READ_S:
        return held[1], held[2]
    try:
        cards = cards_in(directory)
    except OSError:
        cards = []
    return remember(directory, cards, now)


def feed(where):
    """``sizes(now)``: the pit's and the Crypt's shown sizes, or None without a data dir; ``where`` is the data
    dir or a callable giving it."""
    pit, crypt = Grow(), Grow()

    def sizes(now: float):
        root = where() if callable(where) else where
        if root is None:
            return None
        points, rows = read(root, now)
        return pit.step(pit_size(points), now), crypt.step(crypt_size(len(rows)), now)

    return sizes


def switch(path: Path | str | None):
    """The feed for a ``ui/session_rooms.json`` path (its data dir two levels up); none without a path."""
    return feed(Path(path).parent.parent if path is not None else None)
