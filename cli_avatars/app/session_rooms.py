"""START.1: the Dungeon's rooms come from the open orchestrator sessions. No Tk.

The map starts with one room, the Apothecary. Opening a session adds its room on a free slot
around the Apothecary, joined by a short corridor with a door at each end: a simple session gets
a mid room, the main session the large throne room, one main at a time. A live top-level session
whose CLI and project folder match lives in that room, its subagents with it. Ending a session
keeps the room until its avatars have walked back to the Apothecary, then the room goes.
``ui/session_rooms.json`` keeps the open sessions: topic, kind, CLI and slot. No paths.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from cli_avatars.app.dungeon_rooms import load_layout

APOTHECARY = "Apothecary"
SIMPLE, MAIN = "simple", "main"
KINDS = (SIMPLE, MAIN)
CLIS = ("claude", "grok")
SIZES = {SIMPLE: (10, 8), MAIN: (14, 10)}
SLOTS = {MAIN: ("north",), SIMPLE: ("east", "south", "west")}
CLOSE_MAX = 12.0
SCHEMA_VERSION = 1
MAX_BYTES = 16 * 1024
MAX_NAME = 40
_PANTRY = 1

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


@dataclass(frozen=True)
class Session:
    sid: str
    kind: str
    cli: str
    slot: str
    closing: float = 0.0


class SessionRooms:
    """The open sessions, and the layout they give the Dungeon."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.sessions: list[Session] = load(self.path) if self.path is not None else []
        self._cache: tuple = (None, None)

    def open(self, kind: str, cli: str, topic: str) -> str:
        """Add a session; ``""`` when its room is placed, else why not."""
        if kind not in KINDS or cli not in CLIS or not _topic_ok(topic):
            return "Pick simple or main, Claude or Grok, and a project folder."
        if any(s.sid == topic for s in self.sessions):
            return f"{topic} already has a room."
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
        """The Apothecary and one room per live session; the same object while nothing changed."""
        key = tuple((s.sid, s.kind, s.cli, s.slot) for s in self.live(now))
        if self._cache[0] != key:
            self._cache = (key, build_layout(load_layout(), self.live(now)))
        return self._cache[1]

    def _save(self) -> None:
        if self.path is not None:
            save(self.path, [s for s in self.sessions if not s.closing])


def build_layout(base: dict | None, sessions) -> dict | None:
    rooms = (base or {}).get("rooms") or []
    if len(rooms) <= _PANTRY or not isinstance(rooms[_PANTRY], dict):
        return None
    apothecary = copy.deepcopy(rooms[_PANTRY])
    apothecary.update(name=APOTHECARY, origin=[0, 0])
    out = [apothecary]
    for session in sessions:
        out.extend(_slot_rooms(session))
    return {"schema_version": 1, "name": "sessions", "tiling": base.get("tiling"), "rooms": out}


def _slot_rooms(session: Session) -> list[dict]:
    (cu, cv, cw, ch), cdoor = _CORRIDORS[session.slot]
    corridor = _shell(f"~{session.slot}", (cu, cv), (cw, ch), cdoor, _CORRIDOR_LOOK)
    corridor.update(corridor=True, session=session.sid)
    corridor["structure"].append(_torch(cdoor, cw, ch))
    w, h = SIZES[session.kind]
    origin, door = _room_at(session.slot, w, h)
    look = _THRONE_LOOK if session.kind == MAIN else _SIMPLE_LOOKS[SLOTS[SIMPLE].index(session.slot)]
    room = _shell(session.sid, origin, (w, h), door, look)
    room.update(session=session.sid, kind=session.kind, cli=session.cli)
    torches = [(2, 0), (w - 3, 0), (0, 2), (0, h - 2)] + ([(w // 2, 0)] if session.kind == MAIN else [])
    room["structure"] += [_wall_piece("b24-antorcha-der" if y == 0 else "b23-antorcha-izq", x, y)
                          for x, y in torches if (x, y) != door]
    room["structure"] += [{"piece": p, "at": list(at)} for p, at in look["props"]]
    if session.kind == MAIN:
        room["throne"] = True
    return [corridor, room]


def _shell(name: str, origin, size, door, look) -> dict:
    """Floor, back walls with end caps, and the door piece; the front edges stay open."""
    w, h = size
    items = [{"piece": look["floor"], "at": [0, 0], "span": [w, h]}, {"piece": look["corner"], "at": [0, 0]}]
    for x in range(1, w):
        piece = look["cap_r"] if x == w - 1 else look["wall_r"]
        items.append({"piece": look["door_r"] if (x, 0) == door else piece, "at": [x, 0]})
    for y in range(1, h):
        piece = look["cap_l"] if y == h - 1 else look["wall_l"]
        items.append({"piece": look["door_l"] if (0, y) == door else piece, "at": [0, y]})
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
            out.append(Session(sid, kind, cli, slot))
    return out


def save(path: Path, sessions) -> bool:
    """Atomic replace, owner-only, as ``place_store`` does."""
    from events import _restrict_to_user, ensure_private_dir

    if path.is_symlink() or path.parent.is_symlink():
        return False
    rows = [{"sid": s.sid, "kind": s.kind, "cli": s.cli, "slot": s.slot} for s in sessions]
    raw = (json.dumps({"schema_version": SCHEMA_VERSION, "sessions": rows}, indent=2) + "\n").encode("utf-8")
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
        app._session_rooms = found
    return found
