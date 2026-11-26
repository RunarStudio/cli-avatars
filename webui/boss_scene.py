"""BACKLOG-BOSS on the phone (docs/backlog-boss.md): the oni's sprite strip and its state for the map, the Oni Pit
and the Crypt with its skulls (BOSS-ROOM.1). Read-only."""

from __future__ import annotations

import io
import threading
from pathlib import Path

from cli_avatars.app import boss_rooms

FEED_ROWS = 12
CRYPT_ROWS = 40
_LOCK = threading.Lock()
_STRIPS: dict[int, tuple[bytes, int, int, int]] = {}


def sprite_png(stage: int) -> tuple[bytes, int, int, int]:
    """``boss-<stage>``: four idle frames then the defeated pose, bottom-aligned in equal cells."""
    from PIL import Image

    from cli_avatars.app import boss_oni

    with _LOCK:
        if stage in _STRIPS:
            return _STRIPS[stage]
    side = boss_oni.size(stage)
    cell_h = boss_oni.defeated(stage).height
    strip = Image.new("RGBA", (side * 5, cell_h), (0, 0, 0, 0))
    for i in range(5):
        image = boss_oni.frame(stage, i) if i < 4 else boss_oni.defeated(stage)
        strip.paste(image, (i * side, cell_h - image.height), image)
    out = io.BytesIO()
    strip.save(out, "PNG")
    found = (out.getvalue(), side, cell_h, 5)
    with _LOCK:
        _STRIPS[stage] = found
    return found


def state(directory: Path | str, lay: dict, left: int, top: int, px) -> dict | None:
    """HP, stage, the feeding tasks, the week and the pit on the map (``px`` maps a tile to map pixels); the Oni
    Pit's and the Crypt's outlines and the Crypt's skulls (BOSS-ROOM.1)."""
    import time

    import backlog_boss
    from cli_avatars.app.boss_view import pit_room, pit_spot, pit_width
    from cli_avatars.app.room_floor import Plan

    plan = Plan.from_layout(lay)
    spot = pit_spot(plan)
    if spot is None:
        return None
    try:
        found = backlog_boss.public(directory, backlog_boss.cards_in(directory))
    except OSError:
        return None
    found["more"] = max(0, len(found["feeding"]) - FEED_ROWS)
    found["feeding"] = found["feeding"][:FEED_ROWS]
    found["crypt"] = crypt(directory, lay, left, top, px, time.time())
    found["pit_w"] = pit_width(plan)
    found["pit_poly"] = _poly(boss_rooms.room(lay, boss_rooms.PIT_KIND), left, top, px)
    return {**found, "room": pit_room(plan), "at": px(spot[0], spot[1], left, top), "sprite": f"boss-{found['stage']}"}


def _poly(room: dict | None, left: int, top: int, px) -> list:
    if not room:
        return []
    (u, v), (w, h) = room["origin"], room["size"]
    return [px(u, v, left, top), px(u + w, v, left, top), px(u + w, v + h, left, top), px(u, v + h, left, top)]


def crypt(directory: Path | str, lay: dict, left: int, top: int, px, now: float) -> dict | None:
    """The Crypt on the map: its outline, a spot per skull (niches first, then the floor heap) and the forgotten
    cards for its sheet, longest forgotten first."""
    room = boss_rooms.room(lay, boss_rooms.CRYPT_KIND)
    if room is None:
        return None
    rows = boss_rooms.read(directory, now)[1]
    spots = boss_rooms.niches(room)
    heap = boss_rooms.heap(room, max(0, len(rows) - len(spots)))
    skulls = []
    for n, row in enumerate(rows):
        if n < len(spots):
            u, v, _side, lift = spots[n]
        elif n - len(spots) < len(heap):
            u, v, lift = heap[n - len(spots)]
        else:
            break
        x, y = px(u, v, left, top)
        skulls.append({"id": row["id"], "at": [x, y - lift - 1]})
    (u0, v0), (w, h) = room["origin"], room["size"]
    return {"poly": _poly(room, left, top, px), "count": len(rows), "skulls": skulls,
            "plaque": px(u0 + w - 0.6, v0 + h / 2.0, left, top), "rows": rows[:CRYPT_ROWS],
            "more": max(0, len(rows) - CRYPT_ROWS)}
