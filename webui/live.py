"""PHONE.2: who stands where on the phone map. No Tk.

The Dungeon publishes its roster (``set_roster``): every avatar's feet in layout tiles, its room and
look. Without one (``python -m webui`` alone, or the Dungeon hidden) ``fallback`` places them as
START.1 does: you in the Apothecary, one avatar wandering each session room, roamers in the Apothecary.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable

from cli_avatars.app.room_floor import Plan, wander
from cli_avatars.app.session_rooms import APOTHECARY

KINDS = ("user", "orchestrator", "grok", "subagent")
USER_ID = "__you__"
_ROSTER: Callable | None = None


def set_roster(provider: Callable | None) -> None:
    """``provider(layout, now)`` returns rows, or None to use the fallback."""
    global _ROSTER
    _ROSTER = provider


def rows(lay: dict | None, now: float) -> list[dict]:
    provider = _ROSTER
    if provider is not None:
        try:
            found = provider(lay, now)
        except Exception:
            found = None
        if found is not None:
            return list(found)
    return fallback(lay, now)


def fallback(lay: dict | None, now: float, roamers: Iterable[dict] = ()) -> list[dict]:
    """You at the Apothecary's centre, one avatar per session room, ``roamers`` wandering the Apothecary."""
    plan = Plan.from_layout(lay)
    home = plan.floor(APOTHECARY)
    if home is None:
        return []
    out = [{"id": USER_ID, "kind": "user", "name": "You", "room": APOTHECARY, "feet": home.centre(),
            "face": 1, "walk": False}]
    for room in (lay or {}).get("rooms") or []:
        floor = plan.floor(room.get("name", "")) if room.get("kind") else None
        if floor is not None:
            cli = room.get("cli")
            out.append(_walking(floor, f"{cli}:{room['name']}", "grok" if cli == "grok" else "orchestrator",
                                room["name"], now))
    for row in roamers:
        if row.get("kind") in KINDS:
            out.append(_walking(home, str(row["id"]), row["kind"], str(row.get("name") or ""), now))
    return out


def _walking(floor, key: str, kind: str, name: str, now: float) -> dict:
    feet, face = wander(floor, key, now)
    walk = wander(floor, key, now - 0.1)[0] != feet
    return {"id": key, "kind": kind, "name": name, "room": floor.name, "feet": feet, "face": face, "walk": walk}


def dungeon_roster(app, stale: float = 2.0) -> list[dict] | None:
    """The Dungeon's last roster snapshot; None when it is older than ``stale`` seconds (window hidden)."""
    hall = getattr(getattr(app, "places", None), "_hall", None)
    snap = getattr(hall, "snapshot", None)
    if snap is None or time.monotonic() - snap[0] > stale:
        return None
    return snap[1]
