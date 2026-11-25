"""YOU-AVATAR: Daniel's own avatar on the Dungeon floor: where it stands, key steps, its saved spot. No Tk.

Feet are floor tiles (``room_floor``). Arrow keys and WASD walk the way they point on screen: up is ``(-1, -1)`` on
the iso axes. A step that would leave the walkable floor slides along the wall, so the avatar passes through doors
the same way the agents do. The spot is kept in ``ui/you_avatar.json`` (room and feet, no paths). The first spot is
the centre of the throne room when the main session is open, else the Apothecary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cli_avatars.app.room_floor import Plan

STORE = ("ui", "you_avatar.json")
SPEED = 3.2
TAP = 0.3
HOME = "Apothecary"
_R = 0.7071
_KEYS = {"w": (-_R, -_R), "up": (-_R, -_R), "s": (_R, _R), "down": (_R, _R),
         "a": (-_R, _R), "left": (-_R, _R), "d": (_R, -_R), "right": (_R, -_R)}


def direction(keysym: object) -> tuple[float, float] | None:
    """Unit tile step for a WASD or arrow key, as it points on screen."""
    return _KEYS.get(str(keysym).lower())


def heading(held: set[str]) -> tuple[float, float] | None:
    """The sum of the held keys, one tile long; None when they cancel out."""
    du = sum(_KEYS[k][0] for k in held if k in _KEYS)
    dv = sum(_KEYS[k][1] for k in held if k in _KEYS)
    size = (du * du + dv * dv) ** 0.5
    return None if size < 1e-6 else (du / size, dv / size)


def step(plan: Plan, feet: tuple[float, float], way: tuple[float, float], dist: float) -> tuple[float, float]:
    """``feet`` moved ``dist`` tiles along ``way``; a blocked move slides along one axis or stays."""
    u, v = feet
    for du, dv in ((way[0], way[1]), (way[0], 0.0), (0.0, way[1])):
        if abs(du) + abs(dv) < 1e-6:
            continue
        nu, nv = u + du * dist, v + dv * dist
        if plan.walkable(nu, nv):
            return (nu, nv)
    return (u, v)


def facing(way: tuple[float, float], last: int = 1) -> int:
    """Screen x of a tile step is ``du - dv``: right faces 1, left -1."""
    x = way[0] - way[1]
    return last if abs(x) < 1e-6 else (1 if x > 0 else -1)


def home_room(layout: dict | None, plan: Plan) -> str | None:
    """The throne room (the main session's), else the Apothecary, else the last room."""
    for room in (layout or {}).get("rooms") or []:
        if isinstance(room, dict) and room.get("throne") and plan.floor(str(room.get("name"))) is not None:
            return str(room["name"])
    if plan.floor(HOME) is not None:
        return HOME
    rooms = plan.names()
    return rooms[-1] if rooms else None


def store_path(directory: Path | str) -> Path:
    return Path(directory).joinpath(*STORE)


def load(directory: Path | str) -> tuple[str, tuple[float, float]] | None:
    """The saved room and feet; None when missing or bad."""
    try:
        data = json.loads(store_path(directory).read_text(encoding="utf-8"))
        room, feet = data["room"], data["feet"]
        if not isinstance(room, str) or not room or len(feet) != 2:
            return None
        if not all(type(n) in (int, float) for n in feet):
            return None
        return room, (float(feet[0]), float(feet[1]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(directory: Path | str, room: str, feet: tuple[float, float]) -> bool:
    path = store_path(directory)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"room": room, "feet": [round(feet[0], 3), round(feet[1], 3)]}), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def spot(plan: Plan, layout: dict | None, saved) -> tuple[str, tuple[float, float]] | None:
    """Where the avatar stands at start: its saved spot when that room still holds it, else the home room's centre."""
    if saved is not None:
        floor = plan.floor(saved[0])
        if floor is not None and not floor.corridor:
            return saved[0], floor.clamp(*saved[1])
    room = home_room(layout, plan)
    return (room, plan.floor(room).centre()) if room else None
