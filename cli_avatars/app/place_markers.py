"""Subagent sprite markers beside inside orchestrators on the Dungeon scene."""

from __future__ import annotations

from cli_avatars.app import still
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


def bubble_photo(photos, room_scale: int, index: int):
    """AV.1 subagent: one bubble frame, 32x32 native at the rooms scale."""
    from cli_avatars.app.av_roster import LOOKS, SUBAGENT, roster_frame

    look = LOOKS[SUBAGENT]
    registry = REGISTRY
    if registry is None or not hasattr(registry, "has") or not registry.has(look.skin):
        return None
    frame = index % max(1, int(registry.frame_count(look.skin, "idle")))
    image = registry.get_image(look.skin, "idle", frame)
    if image is None:
        return None
    key = ("av1-sub", look, int(room_scale), frame)
    return photos.get(key, lambda: roster_frame(image, look, room_scale, False))


def begin_marks(scene) -> None:
    """A Dungeon frame starts: the ``inside-sub`` images are reused in order (a dead canvas raises)."""
    scene.find_withtag("inside-sub")
    still.pool(scene, "inside-sub").begin()


def settle(scene) -> None:
    """A Dungeon frame ends: unused ``inside-sub`` images go and the floor stays lowest."""
    still.pool(scene, "inside-sub").end()
    still.sink(scene, "floor")


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
    room_scale = getattr(av, "_room_scale", None)
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
        photo = bubble_photo(photos, room_scale, index) if room_scale else inside_sub_photo(photos, skin, size)
        if photo is None:
            continue
        try:
            still.pool(scene, "inside-sub").image(left, top, photo)
        except Exception:
            return
