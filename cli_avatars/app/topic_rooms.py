"""MEMORY.1: Topic rooms on the Dungeon floor. No Tk.

Rooms have a type: Tasks (every room so far: sessions, yours, sandboxes) or Topic. A Topic room comes from a topic
note (``type: topic`` or ``type: resource``, topics are resources) and stands only while its topic is active (an
open task card or a live session room on it), recent (its note updated within ``rooms.topic_recent_days``, default
7) or pinned (``ui/topic_rooms.json``). It is an S room in the Scribe's Nook skin off the Apothecary, else off the
first room with space; double-click opens its card in the Memory tab, and the card's Go to room glides back to it.
"""

from __future__ import annotations

import json
import os
import time
import zlib
from pathlib import Path

from cli_avatars.app import room_place as rp
from cli_avatars.app.custom_rooms import APOTHECARY, APOTHECARY_RECT, SIZE_TILES, CustomRoom, door_cells, room_items

TOPIC, TASKS = "topic", "tasks"
SKIN = "scribes-nook"
RECENT_DAYS = 7
PINS = "ui/topic_rooms.json"
MAX_ROOMS = 4
REREAD_S = 5.0
_LAST: list = [()]


def published(now: float | None = None) -> tuple:
    """The rows the app's feed last gave, for a layout built elsewhere (the phone map)."""
    return _LAST[0]


def room_type(room: dict) -> str:
    return TOPIC if isinstance(room, dict) and room.get("type") == TOPIC else TASKS


def recent_days(config: object) -> float:
    rooms = config.get("rooms") if isinstance(config, dict) else None
    days = rooms.get("topic_recent_days") if isinstance(rooms, dict) else None
    return float(days) if isinstance(days, (int, float)) and not isinstance(days, bool) and days >= 0 \
        else float(RECENT_DAYS)


def load_pins(path: Path) -> list[str]:
    try:
        if Path(path).is_symlink() or not Path(path).is_file():
            return []
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    pins = data.get("pinned") if isinstance(data, dict) else None
    return [p for p in pins if isinstance(p, str) and "/" in p][:64] if isinstance(pins, list) else []


def set_pin(path: Path, key: str, on: bool) -> list[str]:
    """Pin or unpin topic ``key`` (``category/topic``); the saved list."""
    pins = [p for p in load_pins(path) if p != key] + ([key] if on else [])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps({"schema_version": 1, "pinned": pins}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return pins


def why_shown(topic, active: set[str], pins: list[str], now: float, days: float) -> str:
    """``pinned``, ``active`` or ``recent`` when the topic gets a room, else ``""``."""
    if topic.key in pins:
        return "pinned"
    names = {topic.name.lower(), topic.key.lower(), str(topic.meta.get("topic", "")).lower()} - {""}
    if names & {a.lower() for a in active}:
        return "active"
    updated = topic.updated
    if updated and now - updated <= days * 86400:
        return "recent"
    return ""


def shown(topics, active, pins, now: float, days: float) -> list[tuple[str, str, str]]:
    """``(key, room name, why)`` for each topic with a room: pinned first, then active, then most recent."""
    order = {"pinned": 0, "active": 1, "recent": 2}
    rows = [(why_shown(t, set(active), pins, now, days), t) for t in topics]
    rows = sorted(((w, t) for w, t in rows if w), key=lambda r: (order[r[0]], -r[1].updated, r[1].key))
    out, names = [], set()
    for why, topic in rows:
        name = topic.name[:24]
        if name.lower() not in names:
            names.add(name.lower())
            out.append((topic.key, name, why))
    return out[:MAX_ROOMS]


def extend(layout: dict | None, rows, taken) -> dict | None:
    """``layout`` with one Topic room and its corridor per row that finds a free spot and a free name."""
    if layout is None or not rows:
        return layout
    taken, out = list(taken) + _rects_of(layout, "sandbox"), list(layout.get("rooms") or [])
    used = {str(r.get("name", "")).lower() for r in out}
    for key, name, why in rows:
        if name.lower() in used:
            continue
        found = next(((at, p, f) for at, rect in _anchors(out) for p in rp.points(rect)
                      if (f := rp.place(rect, p, SIZE_TILES["S"], taken))), None)
        if found is None:
            continue
        at, point, placed = found
        room = CustomRoom(f"tp-{zlib.crc32(key.encode('utf-8')):08x}", name, "", "S", SKIN, at, point)
        taken += [placed.room, *placed.corridors]
        items = room_items(room, placed, door_cells([room], {room.rid: placed}), _corridor)
        for item in items:
            item.pop("custom", None)
            item["build"] = f"{TOPIC}~{key}"
        items[-1].update(type=TOPIC, memory_topic=key, why=why)
        used.add(name.lower())
        out += items
    return dict(layout, rooms=out)


def _anchors(rooms) -> list[tuple[str, tuple[int, int, int, int]]]:
    """The Apothecary first, then every room already on the map, to hang a Topic room off."""
    out = [(APOTHECARY, APOTHECARY_RECT)]
    for room in rooms:
        if room.get("name") and room.get("name") != APOTHECARY and not room.get("corridor") \
                and isinstance(room.get("origin"), list) and isinstance(room.get("size"), list):
            out.append((room["name"], (*room["origin"], *room["size"])))
    return out


def _rects_of(layout: dict, kind: str) -> list[tuple[int, int, int, int]]:
    """The tile rects of ``kind`` rooms and their corridors already on ``layout``."""
    return [(r["origin"][0], r["origin"][1], r["size"][0], r["size"][1]) for r in layout.get("rooms") or []
            if isinstance(r, dict) and str(r.get("build", "")).startswith(f"{kind}~")]


def topic_of_room(layout: dict | None, name: str) -> str:
    """The ``category/topic`` of Topic room ``name``; ``""`` when it is a Tasks room."""
    for room in (layout or {}).get("rooms") or []:
        if room.get("name") == name and room_type(room) == TOPIC:
            return str(room.get("memory_topic", ""))
    return ""


def room_of_topic(layout: dict | None, key: str) -> str:
    for room in (layout or {}).get("rooms") or []:
        if room_type(room) == TOPIC and room.get("memory_topic") == key:
            return str(room.get("name", ""))
    return ""


def feed(app):
    """``rows(now)`` for ``SessionRooms.topics``: the notes root and the open cards re-read every few seconds."""
    seen: list = [0.0, ()]

    def rows(now: float | None = None) -> tuple:
        now = time.time() if now is None else now
        if now - seen[0] < REREAD_S and seen[0]:
            return seen[1]
        seen[0] = now
        try:
            seen[1] = tuple(shown_now(app, now))
        except Exception:
            seen[1] = ()
        _LAST[0] = seen[1]
        return seen[1]

    return rows


def shown_now(app, now: float) -> list[tuple[str, str, str]]:
    from cli_avatars.app import memory_notes as mn
    from events import app_data_dir

    config = getattr(app, "config", None)
    base = mn.root(config)
    if not mn.exists(base):
        return []
    return shown(mn.room_topics(base), active_topics(app), load_pins(app_data_dir() / PINS), now,
                 recent_days(config))


def active_topics(app) -> set[str]:
    """Topics of open task cards and of live session rooms."""
    from cli_avatars.app.orch_rooms import board_cards

    out: set[str] = set()
    directory = getattr(app, "_chat_directory", None)
    if callable(directory):
        out |= {str(c.get("topic")) for c in board_cards(directory())
                if c.get("topic") and c.get("column") not in ("done", "archived")}
    model = getattr(app, "_session_rooms", None)
    if model is not None:
        out |= {s.sid for s in model.sessions if not s.closing}
    return out


def _corridor(name: str, origin, size, cells) -> dict:
    from cli_avatars.app.session_rooms import _corridor as corridor

    return corridor(name, origin, size, cells)
