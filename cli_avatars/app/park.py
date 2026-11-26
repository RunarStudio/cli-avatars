"""PARK.1: a small night park off the Apothecary where idle avatars sit, train and stroll (docs/park.md). No Tk.

The park is a 12x9 lawn joined to the Apothecary by a short corridor, placed by ``room_place`` on the first free
east or south point of ``POINTS`` (the Apothecary's walls never change) after the session slots and the rooms you
built, so it never overlaps them (a room you build on its spot wins; the park moves to the next point).
``stations`` are where an avatar spends its idle time: two benches, two training dummies, a weight rack, a sparring
post and the stroll path. ``pieces`` are what ``park_art`` draws: grass, three dark sculptures, the benches and
training things, lanterns. ``settings`` reads ``config.json`` ``park`` (``enabled``, ``after_min``) and
``idle_props`` (``enabled``, ``after_s``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cli_avatars.app import room_place as rp
from cli_avatars.app.custom_rooms import APOTHECARY, APOTHECARY_RECT, CustomRoom, door_cells, room_items

KIND = "park"
NAME = "Park"
SIZE = (12, 9)
POINTS = ("e7", "s9", "s1")
SKIN = "moonwell"
AFTER_MIN = 10.0
SHORT_S = 60.0
FLOW_S = 120.0
CONFIG_NAME = "config.json"


@dataclass(frozen=True)
class Settings:
    park: bool = True
    after_s: float = AFTER_MIN * 60.0
    props: bool = True
    short_s: float = SHORT_S
    flow_s: float = FLOW_S


def settings(config: object) -> Settings:
    """``config["park"]`` and ``config["idle_props"]``; a missing or bad value keeps its default."""
    base = Settings()

    def section(name: str) -> dict:
        found = config.get(name) if isinstance(config, dict) else None
        return found if isinstance(found, dict) else {}

    def number(sec: dict, key: str, default: float, unit: float) -> float:
        value = sec.get(key)
        return float(value) * unit if type(value) in (int, float) and value > 0 else default

    def flag(sec: dict, default: bool) -> bool:
        return sec["enabled"] if type(sec.get("enabled")) is bool else default

    park, props = section("park"), section("idle_props")
    return Settings(flag(park, base.park), number(park, "after_min", base.after_s, 60.0), flag(props, base.props),
                    number(props, "after_s", base.short_s, 1.0))


def settings_in(directory: Path | str) -> Settings:
    try:
        return settings(json.loads((Path(directory) / CONFIG_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Settings()


def switch(path: Path | str | None):
    """``on(now)``: whether the park shows, from the data dir's ``config.json`` (read at most every 2 s); a model
    with no data dir has none."""
    if path is None:
        return lambda _now: False
    directory, seen = Path(path).parent.parent, [float("-inf"), True]

    def on(now: float) -> bool:
        if abs(now - seen[0]) > 2.0:
            seen[:] = [now, settings_in(directory).park]
        return seen[1]

    return on


def rects(layout: dict | None) -> list[rp.Rect]:
    """The park's and its corridor's tile rectangles, for what is placed after it."""
    return [(r["origin"][0], r["origin"][1], r["size"][0], r["size"][1]) for r in (layout or {}).get("rooms") or []
            if isinstance(r, dict) and str(r.get("build", "")).startswith(f"{KIND}~")]


def extend(layout: dict | None, taken, enabled: bool = True) -> dict | None:
    """``layout`` with the park and its corridor on the first free point; unchanged when off or nothing fits."""
    if layout is None or not enabled:
        return layout
    found = next(((p, f) for p in POINTS if (f := rp.place(APOTHECARY_RECT, p, SIZE, list(taken)))), None)
    if found is None:
        return layout
    point, placed = found
    room = CustomRoom("park", NAME, "", "M", SKIN, APOTHECARY, point)
    items = room_items(room, placed, door_cells([room], {room.rid: placed}), _corridor)
    for item in items:
        item.pop("custom", None)
        item["build"] = f"{KIND}~{point}"
    lawn = items[-1]
    w, h = lawn["size"]
    kept = [i for i in lawn["structure"] if _keep(i)]
    lawn["structure"] = [{"piece": "b06-roca", "at": [0, 0], "span": [w, h]}, *kept]
    lawn.update(kind=KIND, park=point)
    return dict(layout, rooms=[*(layout.get("rooms") or []), *items])


def _keep(item: dict) -> bool:
    """Only the low garden wall, its pillars and the openings stay; rock under the lawn ``park_art`` paints."""
    return str(item.get("piece", "")).startswith(("b10-", "b11-", "b12-", "b13-", "b14-", "b15-", "b16-", "b25-"))


def _corridor(name: str, origin, size, cells) -> dict:
    from cli_avatars.app.session_rooms import _corridor as corridor

    return corridor(name, origin, size, cells)


def lawn(layout: dict | None) -> dict | None:
    return next((r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("kind") == KIND), None)


@dataclass(frozen=True)
class Piece:
    piece: str
    cell: tuple[int, int]
    flip: bool = False


@dataclass(frozen=True)
class Station:
    oid: str
    act: str
    room: str
    cell: tuple[int, int]
    spots: tuple[tuple[float, float], ...]
    seats: int
    centre: tuple[float, float]


# piece, cell inside the lawn (relative to its origin); the entry corners (u <= 2 or u >= 9, v <= 3) stay clear
_PIECES = (
    ("statue", (4, 1)), ("obelisk", (7, 1)), ("gargoyle", (1, 4)),
    ("lantern", (3, 3)), ("lantern", (9, 2)), ("lantern", (1, 8)), ("lantern", (11, 8)),
    ("bench", (4, 5)), ("bench", (5, 7)), ("dummy", (9, 5)), ("dummy", (9, 7)), ("rack", (7, 5)),
    ("post", (3, 7)),
)
# station id, act, its piece's cell, feet spots (relative), seats
_STATIONS = (
    ("bench-1", "sit", (4, 5), ((4.5, 5.45), (5.5, 5.45)), 2),
    ("bench-2", "sit", (5, 7), ((5.5, 7.45), (6.5, 7.45)), 2),
    ("dummy-1", "hit", (9, 5), ((8.55, 5.6),), 1),
    ("dummy-2", "hit", (9, 7), ((8.55, 7.6),), 1),
    ("rack", "lift", (7, 5), ((7.5, 6.35),), 1),
    ("post", "spar", (3, 7), ((4.3, 7.6),), 1),
    ("stroll", "stroll", (6, 4), ((6.5, 3.4), (8.3, 4.2), (10.4, 5.6), (10.3, 8.4), (7.6, 8.5), (2.6, 5.6)), 8),
)
STROLL_S = 26.0


def pieces(layout: dict | None) -> list[Piece]:
    room = lawn(layout)
    if room is None:
        return []
    (u0, v0) = room["origin"]
    return [Piece(p, (u0 + c[0], v0 + c[1]), i % 2 == 1) for i, (p, c) in enumerate(_PIECES)]


def stations(layout: dict | None) -> list[Station]:
    room = lawn(layout)
    if room is None:
        return []
    (u0, v0) = room["origin"]
    out = []
    for oid, act, cell, spots, seats in _STATIONS:
        out.append(Station(f"park:{oid}", act, room["name"], (u0 + cell[0], v0 + cell[1]),
                           tuple((u0 + a, v0 + b) for a, b in spots), seats, (u0 + cell[0] + 0.5, v0 + cell[1] + 0.5)))
    return out


def stroll_at(station: Station, key: int, now: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where a stroller is on the loop at ``now`` and where it is heading; ``key`` spreads walkers apart."""
    ring = station.spots
    t = (now / STROLL_S + key / 997.0) % 1.0 * len(ring)
    i = int(t)
    a, b = ring[i], ring[(i + 1) % len(ring)]
    k = t - i
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k), b
