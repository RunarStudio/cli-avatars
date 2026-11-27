"""START.1: the Dungeon's rooms come from the open orchestrator sessions. No Tk.

The map starts with one room, the Apothecary. Opening a session adds its room on a free slot
around the Apothecary, joined by a short corridor with a door at each end: a simple session gets
a mid room, the main session the large throne room, one main at a time. A live top-level session
whose CLI and project folder match lives in that room, its subagents with it. Ending a session
keeps the room until its avatars have walked back to the Apothecary, then the room goes.
``ui/session_rooms.json`` keeps the open sessions: topic, kind, CLI and slot. No paths.

ROOMS.1 / PHONE.3: the same model and file hold the rooms you build (name, topic, size, skin and the
point they connect to; ``room_place`` puts each on the nearest free spot, in the order they were made)
and each room's look: the Apothecary and session rooms can be re-skinned, session rooms resized.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from cli_avatars.app import boss_rooms, custom_rooms, park, sandbox_rooms, topic_rooms
from cli_avatars.app import room_place as rp
from cli_avatars.app.custom_rooms import (
    APOTHECARY,
    APOTHECARY_RECT,
    MAX_CUSTOM,
    NO_SPOT,
    RID,
    SIZE_TILES,
    CustomRoom,
    apothecary,
    door_cells,
    fields_why,
    room_items,
    rooms_from,
    title,
)
from cli_avatars.app.dungeon_rooms import load_layout
from cli_avatars.app.room_skins import SKINS, dress

SIMPLE, MAIN = "simple", "main"
KINDS = (SIMPLE, MAIN)
CLIS = ("claude", "grok")
SIZES = {SIMPLE: (10, 8), MAIN: (14, 10)}
SLOTS = {MAIN: ("north",), SIMPLE: ("east", "south", "west")}
CLOSE_MAX = 12.0
SCHEMA_VERSION = 1
MAX_BYTES = 64 * 1024
MAX_NAME = 40
_PANTRY = 1
SESSION_SIZES = {SIMPLE: ("S", "M"), MAIN: ("L",)}


# slot -> corridor (u0, v0, w, h), its door cell, and the room's origin and door cell for a (w, h) room
_CORRIDORS = {
    "north": ((5, -4, 3, 4), (1, 0)),
    "east": ((10, 1, 4, 3), (0, 1)),
    "south": ((5, 8, 3, 4), (1, 0)),
    "west": ((-4, 1, 4, 3), (0, 1)),
}


def _room_at(slot: str, w: int, h: int) -> tuple[tuple[int, int], tuple[int, int] | None]:
    if slot == "north":
        return (6 - w // 2, -4 - h), None
    if slot == "east":
        return (14, 2 - h // 2), (0, h // 2)
    if slot == "south":
        return (6 - w // 2, 12), (w // 2, 0)
    return (-4 - w, 2 - h // 2), None


def _reserved() -> list[tuple[int, int, int, int]]:
    """Every session spot at its largest, corridor and room, so opening a session never meets a built room."""
    out = []
    for kind, slots in SLOTS.items():
        w, h = SIZES[kind]
        for slot in slots:
            out.append(_CORRIDORS[slot][0])
            (u, v), _door = _room_at(slot, w, h)
            out.append((u, v, w, h))
    return out


RESERVED = _reserved()


@dataclass(frozen=True)
class Session:
    sid: str
    kind: str
    cli: str
    slot: str
    closing: float = 0.0
    skin: str = ""
    size: str = ""


class SessionRooms:
    """The open sessions, the rooms you built, and the layout they give the Dungeon."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.sessions: list[Session] = load(self.path) if self.path is not None else []
        self.rooms: list[CustomRoom] = []
        self.looks: dict[str, dict] = {}
        if self.path is not None:
            self.rooms, self.looks = load_custom(self.path)
        self._cache: tuple = (None, None)
        self.sandboxes, self.park_on, self.boss = (lambda now: ()), park.switch(self.path), boss_rooms.switch(self.path)
        self.topics = topic_rooms.published

    def open(self, kind: str, cli: str, topic: str) -> str:
        """Add a session; ``""`` when its room is placed, else why not."""
        if kind not in KINDS or cli not in CLIS or not _topic_ok(topic):
            return "Pick simple or main, Claude or Grok, and a project folder."
        if any(s.sid == topic for s in self.sessions):
            return f"{topic} already has a room."
        if any(r.name.lower() == topic.lower() for r in self.rooms):
            return f"{topic} is the name of one of your rooms: rename that room first."
        if kind == MAIN and any(s.kind == MAIN for s in self.sessions):
            return "One main orchestrator at a time: end it first, or open this one as simple."
        taken = {s.slot for s in self.sessions}
        free = [slot for slot in SLOTS[kind] if slot not in taken]
        if not free:
            return "No free spot for another room: end a simple session first."
        self.sessions.append(Session(topic, kind, cli, free[0]))
        self._save()
        return ""

    def end(self, sid: str, until: float) -> bool:
        """End ``sid``; its room stays until ``until`` so its avatars can walk out."""
        found = next((s for s in self.sessions if s.sid == sid and not s.closing), None)
        if found is None:
            return False
        self.sessions = [replace(s, closing=float(until)) if s is found else s for s in self.sessions]
        self._save()
        return True

    def live(self, now: float) -> list[Session]:
        self.sessions = [s for s in self.sessions if not s.closing or now < s.closing]
        return list(self.sessions)

    def layout(self, now: float) -> dict | None:
        """The Apothecary, a room per live session, your rooms, the sandboxes; the same object while unchanged."""
        extra, on, boss, topics = self.sandboxes(now), self.park_on(now), self.boss(now), self.topics(now)
        key = (tuple((s.sid, s.kind, s.cli, s.slot, s.skin, s.size) for s in self.live(now)),
               tuple(self.rooms), json.dumps(self.looks, sort_keys=True), extra, on, boss, topics)
        if self._cache[0] != key:
            built = park.extend(build_layout(load_layout(), self.live(now), self.rooms, self.looks), self._taken(), on)
            built = boss_rooms.extend(built, self._taken(), boss)
            built = sandbox_rooms.extend(built, extra, self._taken() + park.rects(built) + boss_rooms.rects(built))
            self._cache = (key, topic_rooms.extend(built, topics, self._taken() + park.rects(built)
                                                   + boss_rooms.rects(built) + _rects_of(built, "sandbox")))
        return self._cache[1]

    def add_room(self, name: object, topic: object, size: object, skin: object, at: object, point: object) -> str:
        """Build a room off ``point`` of room ``at``; ``""`` when it is placed and saved, else why not."""
        why = fields_why(name, topic, size, skin) or self._name_why(name, None)
        if why:
            return why
        if len(self.rooms) >= MAX_CUSTOM:
            return f"Up to {MAX_CUSTOM} rooms of your own: delete one first."
        anchor = self._rects().get(at) if isinstance(at, str) else None
        if anchor is None:
            return "Pick a room to connect to: the Apothecary or one of your rooms."
        if rp.parse_point(anchor, point) is None:
            return "Pick a free point of that room."
        used = [int(m.group(1)) for m in (RID.match(r.rid) for r in self.rooms) if m]
        room = CustomRoom(f"room-{max(used, default=0) + 1}", name.strip(), topic.strip(), size, skin, at, point)
        return self._commit(rooms=[*self.rooms, room])

    def edit_room(self, rid: object, name=None, topic=None, size=None, skin=None) -> str:
        """Rename, re-topic, re-skin or resize a room; ``""`` when saved, else why not."""
        if skin is not None and skin not in SKINS:
            return "Pick one of the 30 skins."
        if rid == APOTHECARY:
            if name is not None or topic is not None or size is not None:
                return "The Apothecary keeps its name and size; it can be re-skinned."
            looks = dict(self.looks)
            if skin is not None:
                looks[APOTHECARY] = {"skin": skin}
            return self._commit(looks=looks)
        session = next((s for s in self.sessions if s.sid == rid and not s.closing), None)
        if session is not None:
            if name is not None or topic is not None:
                return "A session room takes its name from its folder; re-skin or resize it."
            if size is not None and size not in SESSION_SIZES[session.kind]:
                return "Session rooms are small or mid; only the main orchestrator's throne room is large."
            changed = replace(session, skin=skin if skin is not None else session.skin,
                              size=size if size is not None else session.size)
            return self._commit(sessions=[changed if s is session else s for s in self.sessions])
        found = next((r for r in self.rooms if r.rid == rid), None)
        if found is None:
            return "No such room."
        changed = replace(found, name=found.name if name is None else name,
                          topic=found.topic if topic is None else topic,
                          size=found.size if size is None else size, skin=found.skin if skin is None else skin)
        why = fields_why(changed.name, changed.topic, changed.size, changed.skin) or self._name_why(changed.name, rid)
        if why:
            return why
        changed = replace(changed, name=changed.name.strip(), topic=changed.topic.strip())
        return self._commit(rooms=[changed if r is found else r for r in self.rooms])

    def delete_room(self, rid: object) -> str:
        """Delete a room you built; the Apothecary and session rooms stay."""
        if rid == APOTHECARY:
            return "The Apothecary stays: re-skin it instead."
        if any(s.sid == rid for s in self.sessions):
            return "End the session to take its room away."
        found = next((r for r in self.rooms if r.rid == rid), None)
        if found is None:
            return "No such room."
        child = next((r for r in self.rooms if r.at == rid), None)
        if child is not None:
            return f"{child.name} connects to it: delete {child.name} first."
        return self._commit(rooms=[r for r in self.rooms if r is not found])

    def plan_room(self, size: object, at: object, point: object) -> str:
        """``""`` when a ``size`` room fits off ``point`` of ``at``, else why not. Saves nothing."""
        anchor = self._rects().get(at) if isinstance(at, str) else None
        if size not in SIZE_TILES or anchor is None or rp.parse_point(anchor, point) is None:
            return "Pick a size, a room and one of its points."
        placed = rp.place(anchor, point, SIZE_TILES[size], self._taken())
        return "" if placed else NO_SPOT.format(size=size, at=title(at, self.rooms), point=point)

    def points(self) -> list[dict]:
        """The rooms you can connect to and their points where at least a small room fits."""
        taken = self._taken()
        rows = []
        for rid, rect in self._rects().items():
            rows.append({"id": rid, "name": title(rid, self.rooms),
                         "points": [p for p in rp.points(rect) if rp.place(rect, p, SIZE_TILES["S"], taken)]})
        return rows

    def catalog(self) -> list[dict]:
        """Every room with what may change: the Apothecary, the live session rooms, then yours."""
        out = [{"id": APOTHECARY, "name": APOTHECARY, "kind": "apothecary", "topic": "", "size": "M", "sizes": [],
                "skin": (self.looks.get(APOTHECARY) or {}).get("skin", ""), "deletable": False, "renamable": False}]
        for s in self.sessions:
            if not s.closing:
                out.append({"id": s.sid, "name": s.sid, "kind": s.kind, "topic": "",
                            "size": s.size or ("L" if s.kind == MAIN else "M"), "sizes": list(SESSION_SIZES[s.kind]),
                            "skin": s.skin, "deletable": False, "renamable": False})
        for r in self.rooms:
            out.append({"id": r.rid, "name": r.name, "kind": "custom", "topic": r.topic, "size": r.size,
                        "sizes": list(SIZE_TILES), "skin": r.skin, "deletable": True, "renamable": True,
                        "at": r.at, "point": r.point})
        return out

    def _rects(self) -> dict[str, rp.Rect]:
        rects = {APOTHECARY: APOTHECARY_RECT}
        placed, _bad = place_rooms(self.rooms)
        for room in self.rooms:
            if room.rid in placed:
                rects[room.rid] = placed[room.rid].room
        return rects

    def _taken(self) -> list[rp.Rect]:
        placed, _bad = place_rooms(self.rooms)
        return [APOTHECARY_RECT, *RESERVED] + [r for p in placed.values() for r in (p.room, *p.corridors)]

    def _name_why(self, name: str, rid: str | None) -> str:
        low = name.strip().lower()
        if low == APOTHECARY.lower() or any(s.sid.lower() == low for s in self.sessions) \
                or any(r.name.lower() == low and r.rid != rid for r in self.rooms):
            return f"{name.strip()} is taken: pick another name."
        return ""

    def _commit(self, sessions=None, rooms=None, looks=None) -> str:
        rooms = self.rooms if rooms is None else rooms
        _placed, bad = place_rooms(rooms)
        if bad is not None:
            return NO_SPOT.format(size=bad.size, at=title(bad.at, rooms), point=bad.point)
        if sessions is not None:
            self.sessions = sessions
        if looks is not None:
            self.looks = looks
        self.rooms = list(rooms)
        self._save()
        return ""

    def _save(self) -> None:
        if self.path is not None:
            save(self.path, [s for s in self.sessions if not s.closing], self.rooms, self.looks)


def _rects_of(layout: dict | None, kind: str) -> list[tuple[int, int, int, int]]:
    """The tile rects of ``kind`` rooms and their corridors already on ``layout``."""
    return [(r["origin"][0], r["origin"][1], r["size"][0], r["size"][1]) for r in (layout or {}).get("rooms") or []
            if isinstance(r, dict) and str(r.get("build", "")).startswith(f"{kind}~")]


def build_layout(base: dict | None, sessions, rooms=(), looks=None) -> dict | None:
    base_rooms = (base or {}).get("rooms") or []
    if len(base_rooms) <= _PANTRY or not isinstance(base_rooms[_PANTRY], dict):
        return None
    placed, _bad = place_rooms(rooms)
    doors = door_cells(rooms, placed)
    skin = ((looks or {}).get(APOTHECARY) or {}).get("skin", "")
    out = [apothecary(base_rooms[_PANTRY], skin if skin in SKINS else "", doors.get(APOTHECARY, {}))]
    for session in sessions:
        out.extend(_slot_rooms(session))
    for room in rooms:
        if room.rid in placed:
            out.extend(room_items(room, placed[room.rid], doors, _corridor))
    return {"schema_version": 1, "name": "sessions", "tiling": base.get("tiling"), "rooms": out}


def place_rooms(rooms) -> tuple[dict, CustomRoom | None]:
    return custom_rooms.place_rooms(rooms, RESERVED)


def _corridor(name: str, origin, size, cells) -> dict:
    return _shell(name, origin, size, None, _CORRIDOR_LOOK, cells)


def _slot_rooms(session: Session) -> list[dict]:
    (cu, cv, cw, ch), cdoor = _CORRIDORS[session.slot]
    corridor = _shell(f"~{session.slot}", (cu, cv), (cw, ch), cdoor, _CORRIDOR_LOOK)
    corridor.update(corridor=True, session=session.sid)
    corridor["structure"].append(_torch(cdoor, cw, ch))
    w, h = SIZE_TILES[session.size] if session.size else SIZES[session.kind]
    origin, door = _room_at(session.slot, w, h)
    look = _THRONE_LOOK if session.kind == MAIN else _SIMPLE_LOOKS[SLOTS[SIMPLE].index(session.slot)]
    if session.skin in SKINS:
        room = {"name": session.sid, "origin": list(origin), "size": [w, h], "floor": 0,
                "structure": dress(session.skin, w, h, {door: "skin"} if door else {}, props=session.kind != MAIN)}
        if session.kind == MAIN:
            room["structure"] += [{"piece": p, "at": list(at)} for p, at in look["props"]]
    else:
        room = _shell(session.sid, origin, (w, h), door, look)
        torches = [(2, 0), (w - 3, 0), (0, 2), (0, h - 2)] + ([(w // 2, 0)] if session.kind == MAIN else [])
        room["structure"] += [_wall_piece("b24-antorcha-der" if y == 0 else "b23-antorcha-izq", x, y)
                              for x, y in torches if (x, y) != door]
        room["structure"] += [{"piece": p, "at": list(at)} for p, at in look["props"] if at[0] < w and at[1] < h]
    room.update(session=session.sid, kind=session.kind, cli=session.cli)
    if session.skin or session.size:
        room["build"] = corridor["build"] = f"{session.sid}~{session.skin}~{session.size}"
    if session.kind == MAIN:
        room["throne"] = True
    return [corridor, room]


def _shell(name: str, origin, size, door, look, doors=()) -> dict:
    """Floor, back walls with end caps, and the door pieces; the front edges stay open."""
    w, h = size
    items = [{"piece": look["floor"], "at": [0, 0], "span": [w, h]}, {"piece": look["corner"], "at": [0, 0]}]
    for x in range(1, w):
        piece = look["cap_r"] if x == w - 1 else look["wall_r"]
        items.append({"piece": look["door_r"] if (x, 0) == door or (x, 0) in doors else piece, "at": [x, 0]})
    for y in range(1, h):
        piece = look["cap_l"] if y == h - 1 else look["wall_l"]
        items.append({"piece": look["door_l"] if (0, y) == door or (0, y) in doors else piece, "at": [0, y]})
    return {"name": name, "origin": list(origin), "size": [w, h], "floor": 0, "structure": items}


def _wall_piece(piece: str, x: int, y: int) -> dict:
    return {"piece": piece, "at": [x, y]}


def _torch(door, w: int, h: int) -> dict:
    return _wall_piece("b24-antorcha-der", w - 1, 0) if door[1] == 0 else _wall_piece("b23-antorcha-izq", 0, h - 1)


_CORRIDOR_LOOK = {"floor": "b01-losa", "corner": "b25-pilar", "wall_r": "b11-muro-der-bajo",
                  "wall_l": "b10-muro-izq-bajo", "cap_r": "b11-muro-der-bajo", "cap_l": "b10-muro-izq-bajo",
                  "door_r": "b14-arco-der", "door_l": "b13-arco-izq"}
_ROOM_WALLS = {"corner": "b12-esquina", "wall_r": "b09-muro-der", "wall_l": "b08-muro-izq",
               "cap_r": "b18-remate-der", "cap_l": "b17-remate-izq", "door_r": "b14-arco-der",
               "door_l": "b13-arco-izq"}
_SIMPLE_LOOKS = (
    dict(_ROOM_WALLS, floor="b02-losa-clara", props=(
        ("o16-estanteria", (1, 1)), ("o10-atril-con-grimorio", (4, 1)), ("o14-mesa-con-vela", (5, 4)),
        ("o14-mesa-con-vela", (7, 4)), ("o11-bola-de-cristal", (2, 5)), ("o27-caja-de-madera", (9, 6)))),
    dict(_ROOM_WALLS, floor="b01-losa", props=(
        ("o30-estante-de-pociones", (1, 1)), ("o12-caldero", (3, 3)), ("o14-mesa-con-vela", (6, 2)),
        ("o13-mesa-larga", (6, 5)), ("o24-barril", (9, 2)), ("o26-pila-de-barriles", (9, 6)))),
    dict(_ROOM_WALLS, floor="b03-losa-oscura", props=(
        ("o16-estanteria", (1, 1)), ("o16-estanteria", (2, 1)), ("o15-banco", (5, 3)),
        ("o14-mesa-con-vela", (3, 5)), ("o02-cofre", (8, 1)), ("o29-botella-azul", (8, 6)))),
)
_THRONE_LOOK = dict(_ROOM_WALLS, floor="b03-losa-oscura", corner="b25-pilar", props=(
    ("o20-brasero", (6, 2)), ("o20-brasero", (6, 8)), ("o16-estanteria", (12, 1)),
    ("o11-bola-de-cristal", (10, 1)), ("o02-cofre", (12, 8))))


def bound_room(layout: dict | None, agent) -> str | None:
    """The session room a live session belongs to: same CLI and project folder. Bots never bind."""
    from claude_chat_hooks import topic_slug

    project = str(getattr(agent, "project", "") or "")
    source = getattr(agent, "source", "")
    if not project or source not in CLIS:
        return None
    topic = topic_slug(project)
    for room in (layout or {}).get("rooms") or []:
        if isinstance(room, dict) and room.get("kind") and room.get("cli") == source \
                and room.get("session") == topic:
            return room.get("name")
    return None


def _topic_ok(topic: object) -> bool:
    from topics import valid_topic_id

    return isinstance(topic, str) and 0 < len(topic) <= MAX_NAME and valid_topic_id(topic) \
        and "/" not in topic and "\\" not in topic and topic != APOTHECARY and not topic.startswith(("~", "."))


def store_path() -> Path:
    from events import app_data_dir

    return app_data_dir() / "ui" / "session_rooms.json"


def load(path: Path) -> list[Session]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return []
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return []
    out: list[Session] = []
    for row in data.get("sessions") or []:
        if not isinstance(row, dict):
            continue
        kind, cli, sid, slot = row.get("kind"), row.get("cli"), row.get("sid"), row.get("slot")
        ok = kind in KINDS and cli in CLIS and _topic_ok(sid) and slot in SLOTS.get(kind, ())
        if ok and all(s.sid != sid and s.slot != slot for s in out) \
                and not (kind == MAIN and any(s.kind == MAIN for s in out)):
            skin = row.get("skin") if row.get("skin") in SKINS else ""
            size = row.get("size") if row.get("size") in SESSION_SIZES[kind] else ""
            out.append(Session(sid, kind, cli, slot, skin=skin, size=size))
    return out


def load_custom(path: Path) -> tuple[list[CustomRoom], dict[str, dict]]:
    """The rooms you built that still fit, in order, and the Apothecary's look."""
    data = _read(path)
    rooms = rooms_from((data or {}).get("rooms"), RESERVED)
    skin = (((data or {}).get("looks") or {}).get(APOTHECARY) or {}).get("skin") \
        if isinstance((data or {}).get("looks"), dict) else None
    return rooms, ({APOTHECARY: {"skin": skin}} if skin in SKINS else {})


def _read(path: Path) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION else None


def save(path: Path, sessions, rooms=(), looks=None) -> bool:
    """Atomic replace, owner-only, as ``place_store`` does."""
    from events import _restrict_to_user, ensure_private_dir

    if path.is_symlink() or path.parent.is_symlink():
        return False
    rows = []
    for s in sessions:
        row = {"sid": s.sid, "kind": s.kind, "cli": s.cli, "slot": s.slot}
        row.update({k: v for k, v in (("skin", s.skin), ("size", s.size)) if v})
        rows.append(row)
    blob = {"schema_version": SCHEMA_VERSION, "sessions": rows}
    if rooms:
        blob["rooms"] = [{"id": r.rid, "name": r.name, "topic": r.topic, "size": r.size, "skin": r.skin,
                          "at": r.at, "point": r.point} for r in rooms]
    if looks:
        blob["looks"] = looks
    raw = (json.dumps(blob, indent=2) + "\n").encode("utf-8")
    try:
        ensure_private_dir(path.parent)
        temporary = path.with_name(path.name + ".tmp")
        if temporary.is_symlink():
            return False
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, path)
    except OSError:
        return False
    _restrict_to_user(path)
    return True


def model_for(app) -> SessionRooms:
    found = getattr(app, "_session_rooms", None)
    if found is None:
        path = None
        if not getattr(getattr(app, "dungeon", None), "_offscreen", True):
            try:
                path = store_path()
            except OSError:
                path = None
        found = SessionRooms(path)
        if callable(getattr(app, "_chat_directory", None)):
            found.sandboxes = sandbox_rooms.feed(app._chat_directory)
        found.topics = topic_rooms.feed(app)
        app._session_rooms = found
    return found
