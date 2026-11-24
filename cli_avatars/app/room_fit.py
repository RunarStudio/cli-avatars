"""Avatar size on the Dungeon rooms floor.

The kit is drawn at an integer scale ``s`` (32x16 tiles, 40 px doors at 1x).
A main avatar's visible body fits a ``MAIN_BOX * s`` square and a subagent a
``SUB_BOX * s`` square, whatever the sheet's frame size, padding or the
desktop ``avatar_scale``. The desktop overlay keeps its own size.
This module does not import tkinter.
"""

from __future__ import annotations

MAIN_BOX = 40
SUB_BOX = 32

_BODY: dict[tuple, tuple[int, int]] = {}


def fit_factor(body_w: float, body_h: float, room_scale: int, box: int = MAIN_BOX) -> float:
    """Resize factor that puts the longer side of the body at ``box * room_scale`` px."""
    longest = max(float(body_w), float(body_h))
    if longest < 1 or room_scale < 1:
        return 1.0
    return box * room_scale / longest


def fitted(width: int, height: int, factor: float) -> tuple[int, int]:
    return max(1, round(width * factor)), max(1, round(height * factor))


def body_size(registry, skin: str, cell: tuple[int, int]) -> tuple[int, int]:
    """Union of the visible pixels across the idle frames. The cell when unknown."""
    key = (skin, tuple(cell))
    if key in _BODY:
        return _BODY[key]
    size = tuple(cell)
    try:
        count = max(1, int(registry.frame_count(skin, "idle")))
        boxes = []
        for index in range(count):
            image = registry.get_image(skin, "idle", index)
            box = image.getchannel("A").getbbox() if image is not None else None
            if box:
                boxes.append(box)
        if boxes:
            size = (max(b[2] for b in boxes) - min(b[0] for b in boxes),
                    max(b[3] for b in boxes) - min(b[1] for b in boxes))
    except Exception:
        size = tuple(cell)
    _BODY[key] = size
    return size


def avatar_factor(av, room_scale: int) -> float:
    base_w, base_h = av._sprite_size()
    registry = getattr(av, "registry", None)
    skin = str(getattr(av.agent, "skin", "") or "")
    if registry is not None and hasattr(registry, "has") and registry.has(skin):
        body_w, body_h = body_size(registry, skin, (base_w, base_h))
    else:
        body_w, body_h = base_w, base_h
    return fit_factor(body_w, body_h, room_scale)


class RoomPhotos:
    """Wraps the shell PhotoCache: same keys plus the factor, frames resized nearest."""

    def __init__(self, photos, factor: float) -> None:
        self._photos = photos
        self.factor = round(float(factor), 4)
        self._own: dict[tuple, object] = {}

    def get(self, key: tuple, factory):
        make = lambda: _resize(factory(), self.factor)  # noqa: E731
        if self._photos is not None:
            return self._photos.get(tuple(key) + ("room", self.factor), make)
        if key not in self._own:
            self._own[key] = make()
        return self._own[key]


def _resize(image, factor: float):
    if image is None or factor == 1.0 or not hasattr(image, "resize") or not hasattr(image, "width"):
        return image
    from PIL import Image

    return image.resize(fitted(image.width, image.height, factor), Image.NEAREST)


def fit_inside(av, photos, room_scale: int):
    """Set the avatar's box for the rooms floor and return the photos to draw with.

    ``room_scale`` 0 means no rooms: the desktop size comes back and photos pass through.
    """
    if room_scale < 1:
        if getattr(av, "_room_scale", None):
            av._room_scale = None
            av.aw, av.ah = av._sprite_size()
        return photos
    factor = avatar_factor(av, room_scale)
    av._room_scale = room_scale
    av.aw, av.ah = fitted(*av._sprite_size(), factor)
    return RoomPhotos(photos, factor)


def child_size(av, default: int) -> int:
    """Subagent marker side: ``SUB_BOX * s`` on the rooms floor, else ``default``."""
    scale = getattr(av, "_room_scale", None)
    return SUB_BOX * scale if scale else default
