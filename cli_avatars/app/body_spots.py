"""BODY places on the room floor, in layout tiles: the bench and its seats, the spot by the door, the smoke source.

The bench stands against the room's back right wall on the first free stretch from the right (a ``bench`` prop slot
wins); the door spot is just inside the room's first door on the way to the user's room; smoke rises from the
room's brazier, else from a chimney on the back wall. No Tk.
"""

from __future__ import annotations

from cli_avatars.app.room_floor import Plan, facing

SEATS = 2
DOOR_IN = (0.7, 1.4, 2.1)
DOOR_GAP = 0.8
BRAZIER = "o20-brasero"


def _cells(room: dict) -> set[tuple[int, int]]:
    """Cells an object or an opening already uses (relative to the room)."""
    out: set[tuple[int, int]] = set()
    for key in ("structure", "desks"):
        for item in room.get(key) or []:
            piece, at = (item.get("piece"), item.get("at")) if isinstance(item, dict) else (None, None)
            if not (isinstance(piece, str) and isinstance(at, list) and len(at) == 2):
                continue
            if piece.startswith("o"):
                out.add((at[0], at[1]))
            elif piece.startswith(("b13-", "b14-", "b15-", "b16-")):
                out.update({(at[0], 1), (at[0] + 1, 1), (at[0] - 1, 1)} if at[1] == 0 else set())
    door = room.get("door")
    if isinstance(door, dict) and isinstance(door.get("at"), list) and door["at"][1:] == [0]:
        u = door["at"][0]
        out.update({(u - 1, 1), (u, 1), (u + 1, 1)})
    return out


def bench(room: dict, seats: int = SEATS) -> tuple[float, float] | None:
    """Absolute tile of the bench's back left corner, ``seats`` tiles long along the back right wall."""
    origin, size = room.get("origin"), room.get("size")
    if not (isinstance(origin, list) and isinstance(size, list)) or room.get("corridor") \
            or room.get("kind") in ("oni-pit", "crypt"):
        return None
    slot = (room.get("prop_slots") or {}).get("bench") if isinstance(room.get("prop_slots"), dict) else None
    if isinstance(slot, list) and len(slot) == 2:
        return (origin[0] + slot[0], origin[1] + slot[1] + 0.1)
    used, width = _cells(room), size[0]
    seats = max(SEATS, seats)
    for u in range(width - 1 - seats, 0, -1):
        if all((u + i, 1) not in used for i in range(seats)):
            return (origin[0] + u, origin[1] + 1.1)
    return None


def seat(corner: tuple[float, float], index: float) -> tuple[float, float]:
    """Feet of the sitter on seat ``index`` (0 is the left seat)."""
    return (corner[0] + 0.5 + index, corner[1] + 0.32)


def door(plan: Plan, room: str, toward: str | None, index: int,
         layout_room: dict | None = None) -> tuple[tuple[float, float], int] | None:
    """Feet and facing of waiter ``index`` just inside the room's door toward ``toward``, clear of furniture."""
    floor = plan.floor(room)
    if floor is None:
        return None
    mine = [d for d in plan.doors if room in (d.a, d.b)]
    hops = plan._hops(room, toward) if toward and toward != room else []
    pick = hops[0][0] if hops and hops[0][0] in mine else (mine[0] if mine else None)
    if pick is None:
        return None
    inside = pick.path[0] if pick.a == room else pick.path[-1]
    mid = pick.path[1]
    du, dv = inside[0] - mid[0], inside[1] - mid[1]
    used = _cells(layout_room) if layout_room else set()
    free = []
    for depth in DOOR_IN:
        for side in (0.0, -DOOR_GAP, DOOR_GAP, -2 * DOOR_GAP, 2 * DOOR_GAP):
            spot = floor.clamp(inside[0] + du * depth - dv * side, inside[1] + dv * depth + du * side)
            cell = (int(spot[0] - floor.u0), int(spot[1] - floor.v0))
            if cell not in used and all(abs(spot[0] - f[0]) + abs(spot[1] - f[1]) > 0.6 for f in free):
                free.append(spot)
    if not free:
        return None
    spot = free[min(index, len(free) - 1)]
    return spot, facing(spot, mid)


def smoke(room: dict) -> tuple[str, tuple[float, float]] | None:
    """``("brazier", tile)`` of the room's first brazier, else ``("chimney", tile)`` on its back right wall."""
    origin, size = room.get("origin"), room.get("size")
    if not (isinstance(origin, list) and isinstance(size, list)) or room.get("corridor"):
        return None
    for item in room.get("structure") or []:
        at = item.get("at") if isinstance(item, dict) else None
        if item.get("piece") == BRAZIER and isinstance(at, list) and len(at) == 2:
            return "brazier", (origin[0] + at[0] + 0.5, origin[1] + at[1] + 0.5)
    return "chimney", (origin[0] + max(1, size[0] - 3) + 0.5, origin[1] + 0.5)
