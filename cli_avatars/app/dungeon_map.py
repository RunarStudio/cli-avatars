"""Scene pixels, the Dungeon canvas, and virtual screen pixels.

The arguments are numbers. This module does not ask Tk where the window is.
Tile math matches the building schema: one floor is ``FLOOR_Z`` units of 16 px.
"""

from __future__ import annotations

import math
from typing import Sequence

FLOOR_Z = 3
TILE_X = 16
TILE_Y = 8
HANDOFF_PX = 8


def zoom_factor(zoom: object) -> int:
    """1, 2, or 3. ``auto`` and anything else draw at 1 until the scene fits."""
    if isinstance(zoom, bool):
        return 1
    if zoom in (1, 2, 3):
        return int(zoom)
    return 1


def tile_to_scene(x: float, y: float, floor: float, x0: float, y0: float) -> tuple[float, float]:
    """North vertex of tile ``(x, y)`` on ``floor``. ``x0, y0`` is the scene origin."""
    return (
        x0 + (x - y) * TILE_X,
        y0 + (x + y) * TILE_Y - floor * FLOOR_Z * TILE_X,
    )


def canvas_from_scene(sx: float, sy: float, zoom: object, pan: Sequence[float]) -> tuple[float, float]:
    z = zoom_factor(zoom)
    return (sx * z + float(pan[0]), sy * z + float(pan[1]))


def scene_from_canvas(dx: float, dy: float, zoom: object, pan: Sequence[float]) -> tuple[float, float]:
    z = zoom_factor(zoom)
    return ((dx - float(pan[0])) / z, (dy - float(pan[1])) / z)


def virtual_from_canvas(dx: float, dy: float, origin: Sequence[float]) -> tuple[float, float]:
    """``origin`` is the canvas top-left in virtual px. It may be negative."""
    return (dx + float(origin[0]), dy + float(origin[1]))


def canvas_from_virtual(vx: float, vy: float, origin: Sequence[float]) -> tuple[float, float]:
    return (vx - float(origin[0]), vy - float(origin[1]))


def scene_to_virtual(
    sx: float, sy: float, zoom: object, pan: Sequence[float], origin: Sequence[float],
) -> tuple[float, float]:
    dx, dy = canvas_from_scene(sx, sy, zoom, pan)
    return virtual_from_canvas(dx, dy, origin)


def virtual_to_scene(
    vx: float, vy: float, zoom: object, pan: Sequence[float], origin: Sequence[float],
) -> tuple[float, float]:
    dx, dy = canvas_from_virtual(vx, vy, origin)
    return scene_from_canvas(dx, dy, zoom, pan)


def client_rect_v(root_x: float, root_y: float, width: float, height: float) -> tuple[float, float, float, float]:
    """Window client box in virtual px: left, top, right, bottom."""
    return (float(root_x), float(root_y), float(root_x) + float(width), float(root_y) + float(height))


def outside_distance(vx: float, vy: float, rect: Sequence[float]) -> float:
    """How far the point sits outside the rect. Zero when it is inside."""
    left, top, right, bottom = (float(v) for v in rect)
    dx = max(left - vx, 0.0, vx - right)
    dy = max(top - vy, 0.0, vy - bottom)
    return math.hypot(dx, dy)


def past_edge(vx: float, vy: float, rect: Sequence[float], margin: float = HANDOFF_PX) -> bool:
    """True once the pointer has left the client rect by more than ``margin`` px."""
    return outside_distance(vx, vy, rect) > float(margin)


def point_inside(vx: float, vy: float, rect: Sequence[float]) -> bool:
    left, top, right, bottom = (float(v) for v in rect)
    return left <= vx <= right and top <= vy <= bottom


def occluded(vx: float, vy: float, covers: Sequence[tuple], dungeon_z: int) -> bool:
    """A cover blocks the point when its z is above the Dungeon and the rect contains it.

    z 0 is the front. A window with a smaller z is in front of a larger z.
    """
    for item in covers:
        z, rect = item[0], item[1]
        if int(z) < int(dungeon_z) and point_inside(vx, vy, rect):
            return True
    return False


def drop_on_dungeon(
    vx: float, vy: float, client: Sequence[float], covers: Sequence[tuple], dungeon_z: int,
) -> bool:
    """Release counts as home when the point is on the client and nothing covers it."""
    return point_inside(vx, vy, client) and not occluded(vx, vy, covers, dungeon_z)


def ring_spot(index: int, count: int, radius: float = 72.0) -> tuple[float, float]:
    """Scene offset for one inside actor. One actor stands at the origin."""
    if count <= 1:
        return (0.0, 0.0)
    turn = -math.pi / 2.0 + (index % count) * (2.0 * math.pi / count)
    return (radius * math.cos(turn), radius * math.sin(turn))


def feet_point(x: float, y: float, width: float, height: float) -> tuple[float, float]:
    """Bottom centre. Hand-off keeps this point on the same virtual pixel."""
    return (x + width / 2.0, y + height)


def body_from_feet(vx: float, vy: float, width: float, height: float) -> tuple[float, float]:
    return (vx - width / 2.0, vy - height)


def door_anchor(width: float, height: float) -> tuple[float, float]:
    """Doorway on the empty floor: bottom centre, inset by the kit door height."""
    return (float(width) / 2.0, max(0.0, float(height) - 72.0))


def border_outside(rect: Sequence[float], x: float, y: float, margin: float = 12.0) -> tuple[float, float]:
    """A point just outside ``rect``, on the edge nearest ``(x, y)``."""
    left, top, right, bottom = (float(v) for v in rect)
    cx = min(max(float(x), left), right)
    cy = min(max(float(y), top), bottom)
    gap = float(margin)
    edges = (
        (cx - left, (left - gap, cy)),
        (right - cx, (right + gap, cy)),
        (cy - top, (cx, top - gap)),
        (bottom - cy, (cx, bottom + gap)),
    )
    return min(edges, key=lambda item: item[0])[1]
