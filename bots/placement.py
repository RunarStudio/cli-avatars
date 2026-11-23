"""Where a shown group stands on the dungeon floor.

The empty floor has no rooms. Each group is then a cluster. A floor that
exposes areas (``group id``, centre x, centre y, in scene pixels from the
middle of the floor) gets one cluster per matching group. Session avatars
have no group and stay on the centre ring, the same ring as today.
"""

from __future__ import annotations

import math
from typing import Sequence

CENTER_RADIUS = 72.0
CLUSTER_RADIUS = 150.0
MEMBER_RADIUS = 28.0


def ring(index: int, count: int, radius: float) -> tuple[float, float]:
    """Same placement as ``dungeon_map.ring_spot`` for the centre radius."""
    if count <= 1:
        return (0.0, 0.0)
    turn = -math.pi / 2.0 + (index % count) * (2.0 * math.pi / count)
    return (radius * math.cos(turn), radius * math.sin(turn))


def scene_offsets(
    items: Sequence[tuple[str, str | None]],
    areas: Sequence[tuple[str, float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Scene-pixel offsets from the floor centre, keyed by actor id."""
    plain: list[str] = []
    order: list[str] = []
    members: dict[str, list[str]] = {}
    for actor_id, group in items:
        if not group:
            plain.append(actor_id)
            continue
        if group not in members:
            order.append(group)
            members[group] = []
        members[group].append(actor_id)
    offsets = {actor_id: ring(index, len(plain), CENTER_RADIUS) for index, actor_id in enumerate(plain)}
    area_map: dict[str, tuple[float, float]] = {}
    if areas:
        for item in areas:
            if len(item) < 3:
                continue
            area_map[str(item[0])] = (float(item[1]), float(item[2]))
    loose = [group for group in order if group not in area_map]
    origins: dict[str, tuple[float, float]] = dict(area_map)
    if len(loose) == 1 and not plain and not area_map:
        origins[loose[0]] = (0.0, 0.0)
    else:
        for index, group in enumerate(loose):
            origins[group] = ring(index, len(loose), CLUSTER_RADIUS)
    for group, origin in origins.items():
        row = members.get(group, [])
        ox, oy = origin
        for index, actor_id in enumerate(row):
            dx, dy = ring(index, len(row), MEMBER_RADIUS if len(row) > 1 else 0.0)
            offsets[actor_id] = (ox + dx, oy + dy)
    return offsets
