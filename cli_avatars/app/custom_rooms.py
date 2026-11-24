"""ROOMS.1 / PHONE.3: the rooms you build, placed in order and dressed in their skins. No Tk.

Each room hangs off a point of the Apothecary or an earlier room; ``room_place`` puts it on the
nearest free spot. ``session_rooms`` keeps them with the open sessions and adds them to the layout.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from cli_avatars.app import room_place as rp
from cli_avatars.app.room_skins import SKINS, dress

APOTHECARY = "Apothecary"
APOTHECARY_RECT = (0, 0, 10, 8)
SIZE_TILES = {"S": (6, 6), "M": (10, 8), "L": (14, 10)}
MAX_CUSTOM = 8
MAX_TOPIC = 60
ROOM_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '-]{0,23}$")
RID = re.compile(r"^room-(\d{1,4})$")
NO_SPOT = "No spot fits a {size} room off {at} {point}: pick another point or a smaller size."
_OPENINGS = ("b13-", "b14-", "b15-", "b16-")


@dataclass(frozen=True)
class CustomRoom:
    """A room you built: placed off ``point`` of room ``at`` (the Apothecary or an earlier room)."""

    rid: str
    name: str
    topic: str
    size: str
    skin: str
    at: str
    point: str


def place_rooms(rooms, reserved) -> tuple[dict[str, rp.Placement], CustomRoom | None]:
    """Each built room placed in order around the Apothecary and ``reserved``; the first that fits nowhere."""
    rects = {APOTHECARY: APOTHECARY_RECT}
    taken = [APOTHECARY_RECT, *reserved]
    placed = {}
    for room in rooms:
        anchor = rects.get(room.at)
        found = rp.place(anchor, room.point, SIZE_TILES[room.size], taken) if anchor else None
        if found is None:
            return placed, room
        placed[room.rid] = found
        rects[room.rid] = found.room
        taken += [found.room, *found.corridors]
    return placed, None


def door_cells(rooms, placed) -> dict:
    """Door cells per owner (a room name, a rid or ``(rid, corridor index)``): ``"skin"`` on a built room."""
    doors: dict = {}
    for room in rooms:
        found = placed.get(room.rid)
        if found is None:
            continue
        chain = [room.at, *[(room.rid, i) for i in range(len(found.corridors))], room.rid]
        for owner, cell in found.doors:
            doors.setdefault(chain[owner], {})[cell] = "skin" if chain[owner] == room.rid else "arch"
    return doors


def apothecary(base_room: dict, skin: str, openings: dict) -> dict:
    """The Apothecary: re-skinned walls, floor and door when it has a skin; arches where rooms connect."""
    room = copy.deepcopy(base_room)
    room.update(name=APOTHECARY, origin=[0, 0])
    if skin:
        w, h = room["size"]
        kept = [i for i in room["structure"] if str(i.get("piece", "")).startswith("o")]
        cells = {tuple(i["at"]): "arch" for i in room["structure"] if str(i.get("piece", "")).startswith(_OPENINGS)}
        cells.update(openings)
        room["structure"] = dress(skin, w, h, cells, props=False) + kept
        if isinstance(room.get("door"), dict):
            style = SKINS[skin].door
            room["door"]["piece"] = "b16-puerta-der" if style == "door" else "b14-arco-der"
        room["build"] = f"{APOTHECARY}~{skin}"
    elif openings:
        room["structure"] = _opened(room["structure"], openings)
    return room


def _opened(items: list[dict], cells: dict) -> list[dict]:
    """Back-wall pieces with an arch at each cell; spans over a cell are split, a torch there goes."""
    out = []
    for item in items:
        at, span = item.get("at"), item.get("span") or [1, 1]
        piece = str(item.get("piece", ""))
        wall = piece.startswith(("b08", "b09", "b10", "b11", "b17", "b18", "b23", "b24"))
        hit = wall and any(at[0] <= x < at[0] + span[0] and at[1] <= y < at[1] + span[1] for x, y in cells)
        if not hit:
            out.append(item)
            continue
        for dx in range(span[0]):
            for dy in range(span[1]):
                cell = (at[0] + dx, at[1] + dy)
                if cell not in cells:
                    out.append({"piece": piece, "at": list(cell)})
    out += [{"piece": "b14-arco-der" if y == 0 else "b13-arco-izq", "at": [x, y]} for x, y in cells]
    return out


def room_items(room: CustomRoom, found: rp.Placement, doors: dict, corridor) -> list[dict]:
    """The room's corridors (``corridor(name, origin, size, cells)`` draws one) and the room in its skin."""
    key = f"{room.rid}~{room.skin}~{room.size}"
    out = []
    for i, (u, v, w, h) in enumerate(found.corridors):
        cells = doors.get((room.rid, i), {})
        piece = corridor(f"~{room.rid}-{i}", (u, v), (w, h), cells)
        piece.update(corridor=True, custom=room.rid, build=key)
        torch = (w - 1, 0) if w >= h else (0, h - 1)
        if torch not in cells:
            piece["structure"].append({"piece": "b24-antorcha-der" if torch[1] == 0 else "b23-antorcha-izq",
                                       "at": list(torch)})
        out.append(piece)
    (u, v, w, h) = found.room
    cells = dict(doors.get(room.rid, {}))
    if "skin" not in cells.values() and (w // 2, 0) not in cells:
        cells[(w // 2, 0)] = "skin"
    out.append({"name": room.name, "origin": [u, v], "size": [w, h], "floor": 0, "custom": room.rid,
                "topic": room.topic, "skin": room.skin, "build": key, "structure": dress(room.skin, w, h, cells)})
    return out


def fields_why(name: object, topic: object, size: object, skin: object) -> str:
    if not isinstance(name, str) or not ROOM_NAME.match(name.strip()):
        return "Name it: up to 24 letters, digits, spaces, ' or -."
    if not isinstance(topic, str) or len(topic) > MAX_TOPIC or not topic.isprintable():
        return f"The topic is one line of up to {MAX_TOPIC} characters."
    if size not in SIZE_TILES:
        return "Pick a size: S, M or L."
    if skin not in SKINS:
        return "Pick one of the 30 skins."
    return ""


def title(rid: str, rooms) -> str:
    return next((r.name for r in rooms if r.rid == rid), rid)


def rooms_from(rows, reserved) -> list[CustomRoom]:
    """The stored rooms that are valid and still fit, in order."""
    rooms: list[CustomRoom] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or len(rooms) >= MAX_CUSTOM:
            continue
        rid, name, topic = row.get("id"), row.get("name"), row.get("topic", "")
        if not (isinstance(rid, str) and RID.match(rid)) or fields_why(name, topic, row.get("size"), row.get("skin")):
            continue
        if any(r.rid == rid or r.name.lower() == name.lower() for r in rooms) \
                or name.lower() == APOTHECARY.lower() or not isinstance(row.get("point"), str):
            continue
        room = CustomRoom(rid, name, topic, row["size"], row["skin"], row.get("at"), row["point"])
        if place_rooms([*rooms, room], reserved)[1] is None:
            rooms.append(room)
    return rooms
