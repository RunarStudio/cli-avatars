"""START.1: a new session room builds in, it does not pop: its pixels rise out of the dark from the
front edge in a dithered sweep, a band of dust runs ahead of the sweep, and the torchlight flares
and settles. ``PlaceBook.draw_inside`` calls ``build_for(book).paint`` each frame; with nothing
being built it returns at once. Frames are the room's own kit pixels, built once per step.
"""

from __future__ import annotations

import math

import numpy as np

from cli_avatars.app.dungeon_rooms import compose, load_manifest
from cli_avatars.app.room_glow import TORCH_ADD, TORCH_GAIN
from cli_avatars.app.throne_px import BAYER

TAG = "room-build"
BUILD_S = 1.4
STEPS = 12
BG = np.array((0x1A, 0x14, 0x22), np.float32)
DUST = np.array((214, 198, 168), np.float32)


def build_for(book) -> RoomBuild:
    found = getattr(book, "_room_build", None)
    if found is None:
        found = RoomBuild()
        book._room_build = found
    return found


class RoomBuild:
    def __init__(self) -> None:
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._layers: dict[tuple, tuple] = {}

    def active(self, painter, now: float) -> list[str]:
        born = getattr(painter, "born", None) or {}
        return sorted(sid for sid, at in born.items() if 0.0 <= now - at < BUILD_S)

    def frame(self, painter, sid: str, elapsed: float):
        """``(RGBA image at 1x, (x, y) in base pixels)`` for ``elapsed`` seconds into the build, or None."""
        from PIL import Image

        layers = self._layers_for(painter, sid)
        if layers is None:
            return None
        plain, behind, mask, at = layers
        t = min(1.0, max(0.0, elapsed / BUILD_S))
        h, w = mask.shape
        yy, xx = np.mgrid[0:h, 0:w]
        rise = 1.0 - yy / max(1, h - 1)
        order = rise * 0.78 + np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0 * 0.22
        front = t * 1.3 - 0.05
        shown = mask & (order < front)
        flare = math.sin(math.pi * min(1.0, max(0.0, (t - 0.25) / 0.75))) * 0.42
        warm = plain[..., :3] * (1.0 + flare * TORCH_GAIN) + flare * TORCH_ADD
        a = behind[..., 3:4] / 255.0
        dark = behind[..., :3] * a + BG * (1.0 - a)
        out = np.zeros((h, w, 4), np.float32)
        out[..., :3] = np.where(shown[..., None], warm, dark)
        seed = (xx * 73856093 ^ yy * 19349663 ^ int(t * STEPS) * 83492791) & 1023
        dust = mask & (order >= front) & (order < front + 0.09) & (seed < 380)
        out[..., :3] = np.where(dust[..., None], DUST, out[..., :3])
        out[..., 3] = np.where(mask, 255.0, 0.0)
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"), at

    def paint(self, scene, painter, now: float) -> None:
        live = self.active(painter, now) if painter is not None else []
        if not live and not self._items:
            return
        for sid in [s for s in self._items if s not in live]:
            scene.delete(self._items.pop(sid))
            self._keys.pop(sid, None)
        if not live:
            self._photos.clear()
            self._layers.clear()
            return
        base, s = painter.base(), painter._scale
        if base is None or not s or painter._center is None:
            return
        for sid in live:
            step = min(STEPS - 1, int((now - painter.born[sid]) / BUILD_S * STEPS))
            key = (id(painter.layout), sid, s, step)
            if key not in self._photos:
                self._photos[key] = self._photo(scene, painter, sid, step, s)
            art = self._photos[key]
            if art is None:
                continue
            photo, (px, py) = art
            x = painter._center[0] - (base.width * s) // 2 + px * s
            y = painter._center[1] - (base.height * s) // 2 + py * s
            item = self._items.get(sid)
            if item is None or not scene.find_withtag(item):
                item = scene.create_image(x, y, image=photo, anchor="nw", tags=("floor", TAG))
                self._items[sid] = item
                scene.tag_raise(item, "rooms")
            else:
                scene.itemconfigure(item, image=photo)
                scene.coords(item, x, y)
            self._keys[sid] = key

    def _photo(self, scene, painter, sid: str, step: int, scale: int):
        from PIL import Image, ImageTk

        made = self.frame(painter, sid, (step + 0.5) / STEPS * BUILD_S)
        if made is None:
            return None
        image, at = made
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        return ImageTk.PhotoImage(image, master=scene), at

    def _layers_for(self, painter, sid: str):
        key = (id(painter.layout), sid)
        if key not in self._layers:
            self._layers[key] = _layers(painter, sid)
        return self._layers[key]


def _layers(painter, sid: str):
    """The room's pixels, what is behind them without the room, the room's mask, its top-left."""
    from PIL import Image

    from cli_avatars.app.throne_stamp import stamp_thrones

    base, layout, manifest = painter.base(), painter.layout, load_manifest()
    if base is None or layout is None or manifest is None:
        return None
    rest = dict(layout, rooms=[r for r in layout.get("rooms") or [] if r.get("session") != sid])
    other = compose(rest, manifest)
    canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    if other is not None:
        stamp_thrones(other, rest)
        left, top = base.info.get("origin", (0, 0))
        ol, ot = other.info.get("origin", (0, 0))
        canvas.alpha_composite(other, (ol - left, ot - top))
    plain = np.asarray(base, dtype=np.float32)
    behind = np.asarray(canvas, dtype=np.float32)
    mask = np.any(plain != behind, axis=-1)
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return plain[y0:y1, x0:x1], behind[y0:y1, x0:x1], mask[y0:y1, x0:x1], (int(x0), int(y0))
