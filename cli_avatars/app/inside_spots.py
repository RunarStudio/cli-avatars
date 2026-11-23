"""Where an inside actor stands. Sessions keep the centre ring.

A bot group clusters off that ring, or on a floor area when the scene
provides ``bot_areas()``. A failure falls back to the ring.
"""

from __future__ import annotations

from cli_avatars.app.dungeon_map import canvas_from_scene, ring_spot


def one_center(book, aid: str, ids) -> tuple[float, float]:
    spots = centers_for(book, list(ids))
    if aid in spots:
        return spots[aid]
    return ring_centers(book, max(1, len(list(ids))))[0]


def centers_for(book, ids) -> dict[str, tuple[float, float]]:
    box = _box(book)
    try:
        from bots.placement import scene_offsets

        items = [(aid, _group(book, aid)) for aid in ids]
        scene = book._scene()
        provider = getattr(scene, "bot_areas", None)
        areas = provider() if callable(provider) else None
        offsets = scene_offsets(items, areas)
        return {aid: _canvas(sx, sy, box) for aid, (sx, sy) in offsets.items()}
    except Exception:
        centers = ring_centers(book, len(ids))
        return {aid: centers[index] for index, aid in enumerate(ids)}


def ring_centers(book, count: int) -> list[tuple[float, float]]:
    box = _box(book)
    return [_canvas(*ring_spot(index, count), box) for index in range(count)]


def _group(book, aid: str):
    av = book.app._inside.get(aid)
    agent = getattr(av, "agent", None)
    if getattr(agent, "source", "") != "bot":
        return None
    return str(getattr(agent, "project", "") or "") or None


def _box(book):
    scene = book._scene()
    width, height = 800, 600
    if scene is not None:
        try:
            width = int(scene.winfo_width())
            height = int(scene.winfo_height())
        except Exception:
            width, height = 800, 600
    if width < 2:
        width = 800
    if height < 2:
        height = 600
    dungeon = getattr(book.app, "dungeon", None)
    zoom = getattr(dungeon, "_zoom", 1)
    pan = getattr(dungeon, "_pan", (0, 0))
    return width, height, zoom, pan


def _canvas(sx, sy, box) -> tuple[float, float]:
    width, height, zoom, pan = box
    dx, dy = canvas_from_scene(sx, sy, zoom, pan)
    return (width / 2.0 + dx, height / 2.0 + dy)
