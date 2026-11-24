"""Subagent sprite markers beside inside orchestrators on the Dungeon scene."""

from __future__ import annotations

from cli_avatars.app.render import photos_for
from cli_avatars.app.room_fit import child_size
from cli_avatars.sprites.registry import REGISTRY
from subskins import assign_subagent_skin

CHILD_SIZE = 32


def subagent_skin_pool() -> list[str]:
    if REGISTRY is not None and hasattr(REGISTRY, "subagent_ids"):
        return list(REGISTRY.subagent_ids())
    return []


def inside_sub_photo(photos, skin: str, size: int, frame: int = 0):
    """One idle-frame subagent sprite scaled to the rooms-floor marker size."""
    registry = REGISTRY
    if registry is None or not hasattr(registry, "has") or not registry.has(skin):
        return None
    image = registry.get_image(skin, "idle", frame)
    if image is None:
        return None
    from cli_avatars.app.room_fit import _resize

    base_w, base_h = registry.get_render_size(skin)
    longest = max(int(base_w), int(base_h), 1)
    factor = float(size) / float(longest)
    image = _resize(image, factor)
    scale = round(factor, 4)
    key = ("inside-sub", skin, size, frame, scale)
    return photos.get(key, lambda: image)


def draw_inside_sub_marks(scene, av, app) -> None:
    """Draw subagent sprites to the right of an inside parent. Tag: ``inside-sub``."""
    count = getattr(av.agent, "subagents", 0)
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        return
    pool = subagent_skin_pool()
    if not pool:
        return
    photos = photos_for(app)
    parent_id = str(getattr(av.agent, "agent_id", "") or "")
    count, size = min(count, 8), child_size(av, CHILD_SIZE)
    for index in range(count):
        left = av.x + av.aw + 6 + index * (size + 4)
        top = av.y + av.ah - size
        skin = assign_subagent_skin(
            getattr(app, "config", None),
            parent_id,
            index,
            pool,
            rng=getattr(app, "_subskin_rng", None),
        )
        photo = inside_sub_photo(photos, skin, size)
        if photo is None:
            continue
        try:
            scene.create_image(left, top, image=photo, anchor="nw", tags=("inside-sub",))
        except Exception:
            return