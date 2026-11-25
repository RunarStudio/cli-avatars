"""SANDBOX on the Dungeon floor: each live sandbox is a small side chamber off the Apothecary. No Tk.

The chamber is an S room in the Ember Cistern skin on the nearest free east or south point (so the Apothecary's
own walls never change), with a short corridor. ``sandbox_art`` stamps the cracks, the rune fence and the warning
brazier on it; ``sandbox_view`` animates them. A chat running in the sandbox's worktree binds to the chamber like a
session to its room: same CLI, same folder name. A promoted or binned sandbox stays ``OUT_S`` so it can animate out.
"""

from __future__ import annotations

import time
from pathlib import Path

from cli_avatars.app import room_place as rp
from cli_avatars.app.custom_rooms import APOTHECARY, APOTHECARY_RECT, SIZE_TILES, CustomRoom, door_cells, room_items
from cli_avatars.app.sandbox_art import KIND, OUT_S

SKIN = "ember-cistern"
POINTS = tuple(p for p in rp.points(APOTHECARY_RECT) if p[0] in "es")


def feed(directory):
    """``rows(now)``: ``(id, folder name, slug, state, ended)`` per sandbox on the map; the store is read on change."""
    import sandbox
    from claude_chat_hooks import topic_slug

    seen: list = [None, ()]

    def rows(now: float | None = None) -> tuple:
        now = time.time() if now is None else now
        try:
            where = directory()
            stamp = sandbox.stamp(where)
            if stamp != seen[0]:
                seen[:] = [stamp, tuple(sandbox.load(where))]
        except Exception:
            return ()
        return tuple((r["id"], Path(r["path"]).name, topic_slug(r["path"]), r["state"], r["ended"]) for r in seen[1]
                     if r["state"] == sandbox.LIVE or 0.0 <= now - r["ended"] < OUT_S)

    return rows


def extend(layout: dict | None, rows, taken) -> dict | None:
    """``layout`` with one chamber and corridor per row that finds a free spot."""
    if layout is None or not rows:
        return layout
    taken, out = list(taken), list(layout.get("rooms") or [])
    for sid, name, slug, state, ended in rows:
        found = next(((p, f) for p in POINTS if (f := rp.place(APOTHECARY_RECT, p, SIZE_TILES["S"], taken))), None)
        if found is None:
            continue
        point, placed = found
        room = CustomRoom(f"sb-{sid[:8]}", name, "", "S", SKIN, APOTHECARY, point)
        taken += [placed.room, *placed.corridors]
        items = room_items(room, placed, door_cells([room], {room.rid: placed}), _corridor)
        for item in items:
            item.pop("custom", None)
            item["build"] = f"{KIND}~{sid}"
        chamber = items[-1]
        chamber["structure"].append({"piece": "o20-brasero", "at": [chamber["size"][0] - 2, 1]})
        chamber.update(kind=KIND, cli="claude", session=slug, sandbox=sid, state=state, ended=ended)
        out += items
    return dict(layout, rooms=out)


def _corridor(name: str, origin, size, cells) -> dict:
    from cli_avatars.app.session_rooms import _corridor as corridor

    return corridor(name, origin, size, cells)
