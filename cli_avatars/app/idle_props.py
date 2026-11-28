"""IDLE-PROPS.1: a few objects in the rooms where idle avatars pass the time, and each project room's task table. No Tk.

Six original objects: a hearth to warm hands (two at once), a dice table for two, a well, a lectern with a book, a
cat with its bowl and a weapon rack to polish. The Apothecary gets the hearth, the table and the well; each other
room gets the next of the lectern, the rack and the cat, then any left go to the Apothecary. A project room (a
session room, or a room you built with a topic) first gets its task table (``task_route``). Each sits on a free
floor tile away from the back wall, the front edges, furniture, every door path and the other objects, nearest a
corner of its own, so doors and corridors stay clear. The same layout gives the same tiles on desktop and phone.
"""

from __future__ import annotations

from dataclasses import dataclass

from cli_avatars.app.room_floor import Plan, facing

KINDS = ("hearth", "dice", "well", "lectern", "rack", "cat")
ACTS = {"hearth": "warm", "dice": "dice", "well": "drink", "lectern": "read", "rack": "polish", "cat": "feed"}
SEATS = {"hearth": 2, "dice": 2}
APOTHECARY_KINDS = 3
DOOR_CLEAR = 2.0
TABLE = "table"
# where in the room each kind would like to stand, as a fraction of its floor
AIM = {"hearth": (0.15, 0.2), "dice": (0.55, 0.6), "well": (0.85, 0.8), "lectern": (0.75, 0.2), "rack": (0.2, 0.75),
       "cat": (0.8, 0.75), TABLE: (0.45, 0.45)}
# feet spots per kind, relative to the object's tile origin
SPOTS = {"hearth": ((0.5, 1.4), (1.4, 0.5)), "dice": ((-0.4, 0.5), (1.4, 0.5)), "well": ((0.5, 1.4),),
         "lectern": ((0.5, 1.35),), "rack": ((1.4, 0.5),), "cat": ((0.5, 1.4),),
         TABLE: ((0.5, 1.4), (-0.4, 0.5), (1.4, 0.5))}


@dataclass(frozen=True)
class Obj:
    oid: str
    kind: str
    room: str
    cell: tuple[int, int]
    seats: int
    spots: tuple[tuple[float, float], ...]
    act: str

    @property
    def centre(self) -> tuple[float, float]:
        return (self.cell[0] + 0.5, self.cell[1] + 0.5)

    def face(self, seat: int) -> int:
        return facing(self.spots[seat], self.centre)


def _rooms(layout: dict | None) -> list[dict]:
    return [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and not r.get("corridor")
            and r.get("kind") not in ("park", "sandbox", "oni-pit", "crypt") and isinstance(r.get("name"), str)]


def project_room(room: dict) -> bool:
    """A session room, or a room you built with a topic: it holds a project's cards."""
    return bool(room.get("kind") in ("simple", "main") or (room.get("custom") and room.get("topic")))


def _used(room: dict) -> set[tuple[int, int]]:
    """Tiles (relative) a piece of furniture, a desk or the circle covers, with the throne's carpet and dais."""
    out = set()
    sizes = _footprints()
    items = [*(room.get("structure") or []), *(room.get("desks") or []), room.get("circle")]
    for item in items:
        piece, at = (item.get("piece"), item.get("at")) if isinstance(item, dict) else (None, None)
        if isinstance(piece, str) and piece.startswith("o") and isinstance(at, list) and len(at) == 2:
            w, h = sizes.get(piece, (1, 1))
            out.update((at[0] + a, at[1] + b) for a in range(max(w, 1)) for b in range(max(h, 1)))
    if room.get("throne"):
        w = room["size"][0]
        out.update((u, v) for u in range(w) for v in range(3, 6))
        out.update((u, v) for u in range(0, 3) for v in range(room["size"][1]))
    return out


class _Finder:
    def __init__(self, layout: dict | None) -> None:
        self.plan = Plan.from_layout(layout)
        self.points = [p for d in self.plan.doors for p in d.path]
        self.taken: set[tuple[int, int]] = set()

    def cell(self, room: dict, kind: str) -> tuple[int, int] | None:
        (u0, v0), (w, h) = room["origin"], room["size"]
        floor = self.plan.floor(room["name"])
        if floor is None:
            return None
        used = {(u0 + a, v0 + b) for a, b in _used(room)}
        aim = (u0 + 1 + (w - 2) * AIM[kind][0], v0 + 1 + (h - 2) * AIM[kind][1])
        best = None
        for u in range(u0 + 2, u0 + w - 1):
            for v in range(v0 + 2, v0 + h - 1):
                if not self._free(u, v, used, floor, kind):
                    continue
                d = (u + 0.5 - aim[0]) ** 2 + (v + 0.5 - aim[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, (u, v))
        if best is None:
            return None
        u, v = best[1]
        self.taken.update((u + a, v + b) for a in (-1, 0, 1) for b in (-1, 0, 1))
        return best[1]

    def _free(self, u: int, v: int, used, floor, kind: str) -> bool:
        near = [(u + a, v + b) for a, b in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))]
        seats = [(int(u + a // 1), int(v + b // 1)) for a, b in SPOTS[kind]]
        if (u, v) in self.taken or any(cell in used for cell in near + seats):
            return False
        if any(abs(p[0] - u - 0.5) + abs(p[1] - v - 0.5) <= DOOR_CLEAR for p in self.points):
            return False
        return all(floor.holds(u + a, v + b) for a, b in SPOTS[kind])


def tables(layout: dict | None) -> dict[str, Obj]:
    """Each project room's task table: its tile and three seats around it."""
    return _place(layout, True)[0]


def place(layout: dict | None, enabled: bool = True) -> list[Obj]:
    """The idle objects of ``layout`` (none when switched off), clear of the task tables."""
    return _place(layout, enabled)[1] if enabled else []


def _place(layout: dict | None, props: bool) -> tuple[dict[str, Obj], list[Obj]]:
    key = (id(layout), props)
    if _CACHE.get("key") == key and _CACHE.get("layout") is layout:
        return _CACHE["value"]
    finder, rooms = _Finder(layout), _rooms(layout)
    found_tables: dict[str, Obj] = {}
    for room in rooms:
        if project_room(room):
            cell = finder.cell(room, TABLE)
            if cell is not None:
                found_tables[room["name"]] = _obj(f"table:{room['name']}", TABLE, room["name"], cell, 3, "work")
    objs: list[Obj] = []
    if props and rooms:
        home, others = rooms[0], rooms[1:]
        plan = [(home, k) for k in KINDS[:APOTHECARY_KINDS]]
        rest = list(KINDS[APOTHECARY_KINDS:])
        for room in others:
            if not rest:
                break
            plan.append((room, rest.pop(0)))
        plan += [(home, k) for k in rest]
        for room, kind in plan:
            cell = finder.cell(room, kind)
            if cell is not None:
                objs.append(_obj(f"{kind}:{room['name']}", kind, room["name"], cell, SEATS.get(kind, 1), ACTS[kind]))
    _CACHE.update(key=key, layout=layout, value=(found_tables, objs))
    return found_tables, objs


_CACHE: dict = {}


def _footprints() -> dict[str, tuple[int, int]]:
    """Kit piece footprints from the manifest, read once."""
    if "footprints" not in _CACHE:
        from cli_avatars.app.dungeon_rooms import load_manifest

        pieces = (load_manifest() or {}).get("pieces") or {}
        _CACHE["footprints"] = {name: tuple(spec["footprint"]) for name, spec in pieces.items()
                                if isinstance(spec, dict) and isinstance(spec.get("footprint"), list)
                                and len(spec["footprint"]) == 2}
    return _CACHE["footprints"]


def _obj(oid: str, kind: str, room: str, cell: tuple[int, int], seats: int, act: str) -> Obj:
    spots = tuple((cell[0] + a, cell[1] + b) for a, b in SPOTS[kind])
    return Obj(oid, kind, room, cell, seats, spots, act)
