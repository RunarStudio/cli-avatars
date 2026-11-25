"""BACKLOG-BOSS on the phone (docs/backlog-boss.md): the oni's sprite strip and its state for the map. Read-only."""

from __future__ import annotations

import io
import threading
from pathlib import Path

FEED_ROWS = 12
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
    """HP, stage, the feeding tasks, the week and the pit on the map (``px`` maps a tile to map pixels)."""
    import backlog_boss
    from cli_avatars.app.boss_view import pit_room, pit_spot
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
    return {**found, "room": pit_room(plan), "at": px(spot[0], spot[1], left, top), "sprite": f"boss-{found['stage']}"}
