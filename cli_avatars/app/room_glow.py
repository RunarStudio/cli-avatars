"""DRAG.GLOW: while an avatar is dragged its room glows with torchlight; the room under it shows a drop hint.

``PlaceBook.draw_inside`` calls ``glow_for(book).paint`` each frame; with nothing dragged and no fade left
it returns at once. The art is the room's own kit pixels, relit warm and dithered, built once per room.
"""

from __future__ import annotations

import math

import numpy as np

from cli_avatars.app import still
from cli_avatars.app.dungeon_rooms import TILE_HALF_H, TILE_HALF_W, compose, load_manifest
from cli_avatars.app.inside_roster import FEET_UP
from cli_avatars.app.room_floor import Plan
from cli_avatars.app.room_rise import rise_for
from cli_avatars.app.throne_px import BAYER

TAG = "room-glow"
FRAME_S = 2.4
FADE_IN, FADE_OUT = 0.25, 0.45
STEPS = 4
TORCH_GAIN = np.array((1.45, 0.95, -0.12), np.float32)
TORCH_ADD = np.array((26.0, 12.0, 0.0), np.float32)
HINT_GAIN = np.array((0.05, 0.3, 0.6), np.float32)
HINT_ALPHA = 0.55
RIM = (255, 236, 186, 210)


def glow_for(book) -> RoomGlow:
    found = getattr(book, "_glow", None)
    if found is None:
        found = RoomGlow()
        book._glow = found
    return found


class RoomGlow:
    """The lit room (``lit`` while held, ``room`` while drawn or fading) and the drop hint room."""

    def __init__(self) -> None:
        self.lit: str | None = None
        self.room: str | None = None
        self.hint: str | None = None
        self._aid = None
        self._on = False
        self._t0 = 0.0
        self._from = 0.0
        self._until = 0.0
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}

    def level(self, now: float) -> float:
        dt = max(0.0, now - self._t0)
        if self._on:
            return min(1.0, self._from + dt / FADE_IN)
        return max(0.0, self._from - dt / FADE_OUT)

    def frame(self, room: str, now: float) -> None:
        """ORCH.ROOM: light ``room`` for ``FRAME_S`` (a Topics row was clicked), then fade."""
        self._from = self.level(now) if room == self.room else 0.0
        self._t0, self._on, self._aid, self._until = now, True, None, now + FRAME_S
        self.lit = self.room = room

    def paint(self, scene, hall, dragging, now: float) -> None:
        if dragging is None and self.room is None:
            if getattr(self, "_rise", None) is not None:
                self._rise.clear(scene)
            return
        self._follow(hall, dragging, now)
        painter = getattr(scene, "_rooms_painter", None)
        level = self.level(now)
        if not self._on and level <= 0.0:
            self.room = None
        step = math.ceil(level * STEPS)
        self._show(scene, painter, "home", self.room, step)
        try:
            rise_for(self).paint(scene, painter, getattr(getattr(hall, "book", None), "app", None), self, now)
        except Exception:
            pass
        self._show(scene, painter, "hint", self.hint, STEPS)

    def _follow(self, hall, dragging, now: float) -> None:
        aid = getattr(getattr(dragging, "agent", None), "agent_id", None)
        if aid is not None and aid != self._aid:
            room = hall.home_room(aid)
            if room is not None:
                self._from = self.level(now) if room == self.room else 0.0
                self._t0, self._on, self._aid = now, True, aid
                self.lit = self.room = room
        elif aid is None and self._on and now >= self._until:
            self._from, self._t0, self._on = self.level(now), now, False
            self.lit, self._aid = None, None
        under = _under(hall, dragging) if self.lit is not None else None
        self.hint = under if under != self.lit else None

    def _show(self, scene, painter, kind: str, room: str | None, step: float) -> None:
        item = self._items.get(kind)
        if room is None or painter is None or step <= 0 or not painter._scale:
            if item is not None:
                scene.delete(item)
                self._items.pop(kind, None)
                self._keys.pop(kind, None)
            return
        key = (kind, room, painter._scale, round(step, 2))
        art = self._photos.get(key)
        if art is None:
            art = self._photos[key] = photo(scene, painter, key)
        if art is None:
            return
        photo_, (px, py) = art
        s = painter._scale
        base = painter.base()
        x = painter._center[0] - (base.width * s) // 2 + px * s
        y = painter._center[1] - (base.height * s) // 2 + py * s
        if item is None or not scene.find_withtag(item):
            item = scene.create_image(x, y, image=photo_, anchor="nw", tags=("floor", TAG))
            self._items[kind] = item
            scene.tag_raise(item, "rooms")
        elif self._keys.get(kind) != key:
            scene.itemconfigure(item, image=photo_)
            still.move(scene, item, x, y)
        else:
            still.move(scene, item, x, y)
        self._keys[kind] = key


def _under(hall, av) -> str | None:
    """Room under a dragged Dungeon avatar's feet, as a drop there would pick it."""
    if av is None or av not in hall.book.app._inside.values():
        return None
    plan = hall.plan()
    if plan is None:
        return None
    feet = (av.x + av.aw / 2.0, av.y + av.ah - FEET_UP * av.ah)
    tile = hall.book._scene()._rooms_painter.to_tile(*feet)
    return plan.room_at(*tile) if tile is not None else None


def photo(scene, painter, key: tuple):
    """Tk image for ``(kind, room, scale, step)`` and its top-left in base pixels."""
    from PIL import Image, ImageTk

    kind, room, scale, step = key
    art, at = _art(painter, room, kind)
    if art is None:
        return None
    rgba = np.asarray(art).copy()
    rgba[..., 3] = (rgba[..., 3].astype(np.float32) * min(1.0, step / STEPS)).astype(np.uint8)
    shown = Image.fromarray(rgba, "RGBA")
    if scale > 1:
        shown = shown.resize((shown.width * scale, shown.height * scale), Image.NEAREST)
    return ImageTk.PhotoImage(shown, master=scene), at


def _art(painter, room: str, kind: str):
    cache = painter.__dict__.setdefault("_glow_art", {})
    if (room, kind) not in cache:
        cache[(room, kind)] = room_art(painter, room, kind)
    return cache[(room, kind)]


def room_art(painter, room: str, kind: str):
    """``(RGBA image, (x, y))`` at 1x: the room's visible kit pixels relit, cropped to them; None, (0, 0) if absent."""
    from PIL import Image

    base = painter.base()
    layout = painter.layout
    floor = Plan.from_layout(layout).floor(room) if base is not None else None
    if floor is None:
        return None, (0, 0)
    left, top = base.info.get("origin", (0, 0))
    rgba = np.asarray(base, dtype=np.float32)
    mask = _owned(layout, floor, base, rgba)
    if not mask.any():
        return None, (0, 0)
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w]
    a, b = (xx + left) / TILE_HALF_W, (yy + top) / TILE_HALF_H
    u, v = (a + b) / 2.0, (b - a) / 2.0
    cu, cv = floor.u0 + floor.w / 2.0 + 0.4, floor.v0 + floor.h / 2.0 + 0.4
    d = np.hypot((u - cu) / (floor.w * 0.7), (v - cv) / (floor.h * 0.7))
    dither = np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0
    out = rgba.copy()
    if kind == "hint":
        k = np.full((h, w), 0.5, np.float32)
        out[..., :3] = rgba[..., :3] * (1.0 + k[..., None] * HINT_GAIN)
        out[..., 3] = np.where(mask, 255.0 * HINT_ALPHA, 0.0)
        out = _rim(out, floor, left, top)
    else:
        f = np.clip(1.0 - d, 0.0, 1.0) ** 1.3 + 0.2
        k = np.floor(f * 6.0 + dither) / 6.0
        out[..., :3] = rgba[..., :3] * (1.0 + k[..., None] * TORCH_GAIN) + k[..., None] * TORCH_ADD
        out[..., 3] = np.where(mask, 255.0, 0.0)
    ys, xs = np.nonzero(out[..., 3] > 0)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = np.clip(out[y0:y1, x0:x1], 0, 255).astype(np.uint8)
    return Image.fromarray(crop, "RGBA"), (int(x0), int(y0))


def _owned(layout: dict, floor, base, rgba) -> np.ndarray:
    """Pixels of the composed rooms that this room's own pieces paint and nothing covers."""
    from PIL import Image

    rooms = [r for r in layout.get("rooms") or [] if isinstance(r, dict)]
    rest = [r for r in rooms if not (r.get("origin") == [floor.u0, floor.v0] and r.get("floor", 0) == 0)]
    manifest = load_manifest()
    other = compose(dict(layout, rooms=rest), manifest) if rest and manifest else None
    behind = np.zeros_like(rgba)
    if other is not None:
        left, top = base.info.get("origin", (0, 0))
        ol, ot = other.info.get("origin", (0, 0))
        canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
        canvas.alpha_composite(other, (ol - left, ot - top))
        behind = np.asarray(canvas, dtype=np.float32)
    return (rgba[..., 3] > 0) & np.any(rgba != behind, axis=-1)


def _rim(out: np.ndarray, floor, left: int, top: int) -> np.ndarray:
    """A dashed pale outline on the room's floor edge."""
    corners = [(floor.u0 + 1, floor.v0 + 1), (floor.u0 + floor.w, floor.v0 + 1),
               (floor.u0 + floor.w, floor.v0 + floor.h), (floor.u0 + 1, floor.v0 + floor.h)]
    pts = [((u - v) * TILE_HALF_W - left, (u + v) * TILE_HALF_H - top) for u, v in corners]
    h, w = out.shape[:2]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=False):
        n = int(max(abs(x1 - x0), abs(y1 - y0)))
        for i in range(n):
            if (i // 3) % 2:
                continue
            x, y = int(x0 + (x1 - x0) * i / n), int(y0 + (y1 - y0) * i / n)
            if 0 <= x < w and 0 <= y < h:
                out[y, x] = RIM
    return out
