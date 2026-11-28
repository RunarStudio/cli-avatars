"""ROOM-ALIGN: one painter's order for the Dungeon floor, back to front by foot point (docs/building-scene.md).

Tiles, kit pieces, idle objects, benches and avatars share one key: the foot point in tiles, row ``u + v`` first
(further up the screen is further back), then column ``u - v`` (left before right). A wall stands on the back edge
of its tile, a piece on its footprint, an avatar on its feet. The composed rooms image stays the floor; every
standing kit piece is also a canvas item above it (``occluder``), and ``restack`` slips each moving item just under
the first standing piece it is behind, so a wall, a pillar or a desk in front hides it and nothing behind does.
"""

from __future__ import annotations

from dataclasses import dataclass

OCCLUDER = "occluder"
WALL_T = 0.15
PILLAR = 0.5
BENCH_DEPTH = 0.6
FLAT_PAD = 6
EPS = 1e-6


def key(u: float, v: float) -> tuple[float, float]:
    """Painter's order of a foot point: row, then column."""
    return (round(u + v, 4), round(u - v, 4))


@dataclass(frozen=True)
class Box:
    """Floor extent in tiles: ``u0..u1`` by ``v0..v1``; a point has ``u0 == u1`` and ``v0 == v1``."""
    u0: float
    u1: float
    v0: float
    v1: float

    @classmethod
    def point(cls, u: float, v: float) -> "Box":
        return cls(u, u, v, v)

    @property
    def foot(self) -> tuple[float, float]:
        return ((self.u0 + self.u1) / 2.0, (self.v0 + self.v1) / 2.0)


def behind(a: Box, b: Box) -> bool:
    """``a`` is on the back side of ``b`` along an axis and not in front of it along the other."""
    if a.u0 >= b.u1 - EPS or a.v0 >= b.v1 - EPS:
        return False
    return a.u1 <= b.u0 + EPS or a.v1 <= b.v0 + EPS


def piece_box(name: str, spec: dict, u: int, v: int) -> Box:
    """Where a kit piece stands: a right wall on its tile's back edge along ``u``, a left wall along ``v``, a corner
    or pillar at the back corner, a hung piece on its wall, anything else on its footprint."""
    fw, fh = _pair(spec.get("footprint"), (1, 1))
    category = spec.get("category")
    if category in ("wall", "door") or (fw, fh) == (0, 0):
        if "-der" in name:
            return Box(u, u + 1, v, v + WALL_T)
        if "-izq" in name:
            return Box(u, u + WALL_T, v, v + 1)
        return Box(u, u + PILLAR, v, v + PILLAR)
    return Box(u, u + max(fw, 1), v, v + max(fh, 1))


def standing(spec: dict) -> bool:
    """A piece that rises above the floor; rugs, decals, floor tiles and light pools lie flat."""
    category = spec.get("category")
    if category in ("floor", "decal", "rock"):
        return False
    size = _pair(spec.get("size"), (0, 0))
    fw, fh = _pair(spec.get("footprint"), (1, 1))
    if (fw, fh) == (0, 0):
        return category != "light" or size[0] <= 16
    if category == "light":
        return False
    return size[1] > (fw + fh) * 4 + FLAT_PAD


def _pair(value, default) -> tuple[int, int]:
    if isinstance(value, list) and len(value) == 2 and all(type(n) is int for n in value):
        return value[0], value[1]
    return default


def overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def slot(box: Box, bbox, occluders) -> int | None:
    """Index of the first occluder (in paint order) that overlaps ``bbox`` on screen and stands in front of ``box``;
    None when nothing in front covers it."""
    for index, (o_box, o_bbox) in enumerate(occluders):
        if overlap(bbox, o_bbox) and behind(box, o_box):
            return index
    return None


def restack(scene, items, occluders, ids) -> None:
    """Put each ``(box, canvas id)`` of ``items`` under the first occluder in front of it, else above them all.

    ``occluders`` are ``(box, canvas bbox)`` in paint order with their canvas ``ids``. Items go back to front, so two
    under the same occluder keep their own order.
    """
    if not ids:
        return
    top = ids[-1]
    for box, item in sorted(items, key=lambda row: key(*row[0].foot)):
        try:
            bbox = scene.bbox(item)
            index = slot(box, bbox, occluders) if bbox else None
            if index is None:
                scene.tag_raise(item, top)
                top = item
            else:
                scene.tag_lower(item, ids[index])
        except Exception:
            continue


def floor_items(book, painter, dragging=None) -> list[tuple[Box, int]]:
    """The moving things on the floor this frame: inside avatars by their feet, idle objects, task tables and benches
    by their tiles. The dragged avatar stays on top."""
    out: list[tuple[Box, int]] = []
    for av in (getattr(book.app, "_inside", None) or {}).values():
        item = getattr(av, "spr_id", None)
        if item is None or av is dragging:
            continue
        try:
            pad = av._foot_pad()
        except Exception:
            pad = 0
        feet = painter.to_tile(av.x + av.aw / 2.0, av.y + av.ah - pad)
        if feet is not None:
            out.append((Box.point(*feet), item))
    life = getattr(book, "_life", None)
    if life is not None:
        cells = {o.oid: o.cell for o in life.objs}
        cells.update({f"table:{name}": t.cell for name, t in life.tables.items()})
        for name, item in life._items.items():
            if name in cells:
                u, v = cells[name]
                out.append((Box(u, u + 1, v, v + 1), item))
    body = getattr(book, "_body", None)
    for name, ((u, v), seats) in (getattr(body, "benches", None) or {}).items():
        item = body._items.get(f"bench:{name}")
        if item is not None:
            out.append((Box(u, u + seats, v, v + BENCH_DEPTH), item))
    return out


def stack(book, scene, painter, dragging=None, building=()) -> None:
    """After the frame is drawn: the standing pieces right above the floor items, each moving thing slotted in."""
    if painter is None or not callable(getattr(painter, "occluders", None)):
        return
    painter.hold_back(scene, set(building))
    occluders, ids = painter.occluders()
    if not ids:
        return
    scene.tag_raise(OCCLUDER, "floor")
    restack(scene, floor_items(book, painter, dragging), occluders, ids)


def settle(book, scene, dragging, now) -> None:
    """End of a frame: the floor at the bottom, the standing pieces and moving things in depth order, labels under
    the HUD."""
    from cli_avatars.app.hud_fit import labels_under
    from cli_avatars.app.room_build import build_for

    scene.tag_lower("floor")
    painter = getattr(scene, "_rooms_painter", None)
    try:
        stack(book, scene, painter, dragging, build_for(book).active(painter, now) if painter else ())
        labels_under(scene, book.app._inside)
    except Exception:
        return
