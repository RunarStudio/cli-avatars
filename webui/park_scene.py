"""PARK.1 + IDLE-PROPS.1 on the phone map: the park, the idle objects and the task tables. No Tk.

``stamp`` paints the park, each idle object (at rest) and each project room's bare task table into the composed
map, the same pixels as the Dungeon. ``state`` gives the page what moves or changes: each table's doing and todo
titles, the park's lamps and box for the fireflies, and where the objects stand. All in map pixels.
"""

from __future__ import annotations

from pathlib import Path

from cli_avatars.app import idle_art, idle_props, park, park_art, task_route
from cli_avatars.app.dungeon_rooms import TILE_HALF_H, TILE_HALF_W
from cli_avatars.app.park_px import paste

TITLE_CHARS = 40


def props_on(directory: Path | str) -> bool:
    return park.settings_in(directory).props


def stamp(image, lay: dict | None, props: bool) -> None:
    park_art.stamp(image, lay)
    left, top = image.info.get("origin", (0, 0))
    things = [(o.cell, idle_art.frame(o.kind, False, 0)) for o in idle_props.place(lay, props)]
    things += [(t.cell, idle_art.table(0, 0, 0)) for t in idle_props.tables(lay).values()]
    for cell, sprite in sorted(things, key=lambda row: (row[0][0] + row[0][1], row[0][0])):
        x, y = _global(cell[0] + 0.5, cell[1] + 0.5)
        paste(image, sprite, x - left, y - top)


def state(directory: Path | str, lay: dict | None, left: int, top: int, cards: list) -> dict:
    """The page's part: tables with their titles, idle objects, the park's lamps and box (empty when off)."""
    px = lambda u, v: [round(_global(u, v)[0] - left), round(_global(u, v)[1] - top)]  # noqa: E731
    tables = [{"room": t.room, "at": px(t.cell[0] + 0.5, t.cell[1] + 0.5), "blocked": t.blocked,
               "doing": [s[:TITLE_CHARS] for s in t.doing], "todo": [s[:TITLE_CHARS] for s in t.todo]}
              for t in task_route.tables(lay, cards).values()]
    props = [{"kind": o.kind, "act": o.act, "room": o.room, "at": px(*o.centre)}
             for o in idle_props.place(lay, props_on(directory))]
    found = park_art.fx_inputs(lay)
    if found is None:
        return {"tables": tables, "props": props, "lamps": [], "box": None}
    (x0, y0, w, h), lamps = found[0], found[1]
    return {"tables": tables, "props": props, "lamps": [[round(x - left), round(y - top)] for x, y in lamps],
            "box": [round(x0 - left), round(y0 - top), w, h]}


def _global(u: float, v: float) -> tuple[float, float]:
    return ((u - v) * TILE_HALF_W, (u + v) * TILE_HALF_H)
