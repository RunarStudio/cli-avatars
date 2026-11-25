"""FOCUS on the Dungeon floor: the focused task's room stays lit, every other room goes dark, and a banner says so.

Drawn in code from the room kit's own pixels, as ``room_glow`` does: other rooms and corridors under a cool dark
veil, dithered, their torches snuffed to soot, a little light spilling from the lit room onto its neighbours; the
lit room's torches burn brighter with a warm flickering halo. The banner on top of the scene names the task, shows
a red wax seal with how many alerts wait, and holds **Leave focus**. All are canvas items made once and changed in
place (images swap only when their key changes), so nothing blinks; no window opens.
"""

from __future__ import annotations

import math

import numpy as np

import focus
from cli_avatars.app import focus_mode
from cli_avatars.app.dungeon_rooms import TILE_HALF_H, TILE_HALF_W
from cli_avatars.app.room_floor import Plan
from cli_avatars.app.room_glow import _owned
from cli_avatars.app.session_rooms import APOTHECARY
from cli_avatars.app.throne_model import GOLD, label
from cli_avatars.app.throne_px import BAYER, Buf, t35, to_image, tone

TAG = "focus-veil"
BANNER = "focus-banner"
LEAVE = "focus-leave"
FADE_IN, FADE_OUT = 0.5, 0.35
STEPS = 4
FLICKER = (1.0, 0.82, 0.94, 0.88)
NIGHT = np.array((8.0, 10.0, 26.0), np.float32)
SOOT = np.array((46.0, 36.0, 38.0), np.float32)
WHITE_HOT = np.array((255.0, 250.0, 214.0), np.float32)
HALO = np.array((58.0, 30.0, 4.0), np.float32)
INK, BOARD, BOARD_LO, SEAL, SEAL_LO, SEAL_INK = "#f0e6c8", "#1a1226", "#0c0812", "#c0283c", "#6e1020", "#ffe6b0"


def veil_for(book) -> "Veil":
    found = getattr(book, "_focus_veil", None)
    if found is None:
        found = book._focus_veil = Veil()
    return found


def paint(book, scene, hall, now: float) -> None:
    try:
        veil_for(book).paint(book.app, scene, now)
    except Exception:
        return


def flames(rgb: np.ndarray) -> np.ndarray:
    """Torch fire pixels of the kit: bright, warm, red over blue."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r >= 200) & (g >= 130) & (r >= g) & (r - b >= 30)


def _blur(m: np.ndarray, r: int) -> np.ndarray:
    """Two box passes each way: a soft round falloff around ``m``."""
    out = m.astype(np.float32)
    for _ in range(2):
        for axis in (0, 1):
            pad = np.pad(out, [(r + 1, r) if a == axis else (0, 0) for a in (0, 1)])
            c = np.cumsum(pad, axis=axis)
            hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
            lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
            out = (hi - lo) / (2 * r + 1)
    return out


def art(painter, room: str):
    """At 1x: the veil over everything but ``room`` (full map size) and the lit room's flicker frames with their
    top-left. Cached on the painter until the map is composed again."""
    cache = painter.__dict__.setdefault("_focus_art", {})
    base = painter.base()
    key = (id(base), room)
    if key not in cache:
        cache.clear()
        cache[key] = _art(painter.layout, base, room)
    return cache[key]


def _art(layout: dict, base, room: str):
    from PIL import Image

    rgba = np.asarray(base, dtype=np.float32)
    h, w = rgba.shape[:2]
    floor = Plan.from_layout(layout).floor(room)
    mine = _owned(layout, floor, base, rgba) if floor is not None else np.zeros((h, w), bool)
    left, top = base.info.get("origin", (0, 0))
    yy, xx = np.mgrid[0:h, 0:w]
    dither = np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0
    if floor is not None:
        a, b = (xx + left) / TILE_HALF_W, (yy + top) / TILE_HALF_H
        u, v = (a + b) / 2.0, (b - a) / 2.0
        du = np.maximum(np.maximum(floor.u0 - u, u - (floor.u0 + floor.w)), 0.0)
        dv = np.maximum(np.maximum(floor.v0 - v, v - (floor.v0 + floor.h)), 0.0)
        spill = 0.26 * np.exp(-np.hypot(du, dv) / 2.2)
    else:
        spill = np.zeros((h, w), np.float32)
    k = (np.floor((0.26 + spill) * 12.0 + dither) / 12.0)[..., None]
    rgb = rgba[..., :3]
    dark = rgb * k + NIGHT * (1.0 - k) * 0.6
    dark = np.where(flames(rgb)[..., None], SOOT * (0.7 + 0.3 * dither[..., None]), dark)
    veil = np.zeros_like(rgba)
    veil[..., :3] = dark
    veil[..., 3] = np.where((rgba[..., 3] > 0) & ~mine, 255.0, 0.0)
    veil_image = Image.fromarray(np.clip(veil, 0, 255).astype(np.uint8), "RGBA")
    frames, at = [], (0, 0)
    if mine.any():
        ys, xs = np.nonzero(mine)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        fire = flames(rgb) & mine
        halo = _blur(fire, 10)
        halo = np.clip(halo / max(1e-6, float(halo.max())) * 1.6, 0.0, 1.0) if fire.any() else halo
        for f in FLICKER:
            lit = rgb * 1.06 + (np.floor(halo * f * 6.0 + dither) / 6.0)[..., None] * HALO * 1.6
            lit = np.where(fire[..., None], rgb + (WHITE_HOT - rgb) * 0.55 * f, lit)
            out = np.zeros_like(rgba)
            out[..., :3] = lit
            out[..., 3] = np.where(mine, 255.0, 0.0)
            frames.append(Image.fromarray(np.clip(out[y0:y1, x0:x1], 0, 255).astype(np.uint8), "RGBA"))
        at = (int(x0), int(y0))
    return veil_image, frames, at


def banner_image(title: str, waiting: int):
    """The banner at 1x: a dark board with a gold rim, a lit candle, FOCUS and the task, and the wax seal."""
    text = f"FOCUS  {label(title, 34) or 'TASK'}"
    tail = f"{waiting} WAITING" if waiting else "ALERTS HELD"
    width = 6 + 7 + len(text) * 4 + 8 + 13 + 3 + len(tail) * 4 + 6
    b = Buf(width, 17)
    b.rect(0, 1, width, 16, BOARD_LO)
    b.rect(0, 0, width, 16, tone(GOLD, 0.55))
    b.rect(1, 1, width - 2, 14, BOARD)
    b.rect(1, 1, width - 2, 1, tone(GOLD, 0.8))
    for x, y in ((0, 0), (width - 1, 0), (0, 15), (width - 1, 15)):
        b.px(x, y, GOLD)
    b.rect(7, 8, 3, 5, "#e8dcc0")
    b.rect(7, 12, 3, 1, "#a89880")
    b.px(8, 7, "#4a3a30")
    for x, y, c in ((8, 4, "#ffd76a"), (8, 5, "#fff4d6"), (8, 6, "#ffb030"), (7, 5, "#ff9a2a"), (9, 5, "#ff9a2a"),
                    (8, 3, "#ff8a20")):
        b.px(x, y, c)
    x = 13
    x += t35(b, x, 6, text, INK, sh="#08060c") + 8
    seal = SEAL if waiting else tone(SEAL, 0.45)
    for dy in range(13):
        for dx in range(13):
            d = math.hypot(dx - 6, dy - 6)
            if d <= 6.4:
                b.px(x + dx, 2 + dy, SEAL_LO if d > 5.4 or dy > 9 else seal)
    t35(b, x + 7, 6, str(min(waiting, 99)), SEAL_INK, align="c", sh=SEAL_LO)
    t35(b, x + 16, 6, tail, "#ff9aa0" if waiting else "#8a8098", sh="#08060c")
    return to_image(b)


def leave_image(hot: bool = False):
    """The Leave focus button: a raised wine plate, gold when the pointer is on it."""
    text = "LEAVE FOCUS"
    width = len(text) * 4 + 11
    b = Buf(width, 17)
    face = "#e0a83c" if hot else "#7a2436"
    b.rect(0, 1, width, 16, BOARD_LO)
    b.rect(0, 0, width, 16, tone(face, 0.6))
    b.rect(1, 1, width - 2, 13, face)
    b.rect(1, 1, width - 2, 1, tone(face, 1.3))
    t35(b, 6, 5, text, "#1a1226" if hot else INK, sh=None if hot else "#3a0c18")
    return to_image(b)


class Veil:
    def __init__(self) -> None:
        self.room: str | None = None
        self._on = False
        self._t0 = 0.0
        self._from = 0.0
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._hot = False
        self._made: dict[tuple, object] = {}
        self._app = None

    def level(self, now: float) -> float:
        dt = max(0.0, now - self._t0)
        if self._on:
            return min(1.0, self._from + dt / FADE_IN)
        return max(0.0, self._from - dt / FADE_OUT)

    def paint(self, app, scene, now: float) -> None:
        state = focus_mode.state(app)
        painter = getattr(scene, "_rooms_painter", None)
        layout = getattr(painter, "layout", None) or {}
        room = focus.room_of(layout.get("rooms") or [], state["topic"], APOTHECARY) if state["task"] else None
        if (room is not None) != self._on or (room is not None and room != self.room):
            self._from, self._t0 = (self.level(now) if room is None or self.room is None else 0.0), now
            self._on = room is not None
        if room is not None:
            self.room = room
        level = self.level(now)
        if painter is None or not painter._scale or painter.base() is None or level <= 0.0:
            self.room = None if level <= 0.0 else self.room
            self.clear(scene)
            return
        veil, frames, at = art(painter, self.room)
        step = math.ceil(level * STEPS)
        self._image(scene, painter, "veil", (id(veil), self.room, painter._scale, step), veil, (0, 0), step)
        if frames:
            n = int(now * 7) % len(frames)
            self._image(scene, painter, "light", (id(frames[n]), self.room, painter._scale, step), frames[n], at, step)
        if self._on:
            self._banner(app, scene, state, max(2, int(painter._scale)))
        else:
            self._drop(scene, "banner")
            self._drop(scene, "leave")

    def clear(self, scene) -> None:
        for kind in list(self._items):
            self._drop(scene, kind)

    def _drop(self, scene, kind: str) -> None:
        item = self._items.pop(kind, None)
        self._keys.pop(kind, None)
        if item is not None:
            scene.delete(item)

    def _photo(self, scene, key: tuple, image, scale: int, alpha: float = 1.0):
        photo = self._photos.get(key)
        if photo is None:
            from PIL import Image, ImageTk

            if alpha < 1.0:
                rgba = np.asarray(image).copy()
                rgba[..., 3] = (rgba[..., 3].astype(np.float32) * alpha).astype(np.uint8)
                image = Image.fromarray(rgba, "RGBA")
            if scale > 1:
                image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
            if len(self._photos) > 24:
                self._photos.clear()
            photo = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
        return photo

    def _image(self, scene, painter, kind: str, key: tuple, image, at: tuple, step: int) -> None:
        s = painter._scale
        base = painter.base()
        x = painter._center[0] - (base.width * s) // 2 + at[0] * s
        y = painter._center[1] - (base.height * s) // 2 + at[1] * s
        self._place(scene, kind, key, lambda: self._photo(scene, key, image, s, step / STEPS), x, y, "nw",
                    ("floor", TAG))
        scene.tag_raise(self._items[kind], "rooms")

    def _place(self, scene, kind: str, key: tuple, photo, x: float, y: float, anchor: str, tags: tuple) -> None:
        item = self._items.get(kind)
        if item is None or not scene.find_withtag(item):
            item = self._items[kind] = scene.create_image(x, y, image=photo(), anchor=anchor, tags=tags)
            self._keys[kind] = key
            if kind == "leave":
                scene.tag_bind(item, "<Button-1>", lambda _e: self._leave(scene))
                scene.tag_bind(item, "<Enter>", lambda _e: self._hover(scene, True))
                scene.tag_bind(item, "<Leave>", lambda _e: self._hover(scene, False))
        elif self._keys.get(kind) != key:
            scene.itemconfigure(item, image=photo())
            self._keys[kind] = key
        if tuple(scene.coords(item)) != (float(x), float(y)):
            scene.coords(item, x, y)

    def _banner(self, app, scene, state: dict, k: int) -> None:
        self._app = app
        key = ("banner", state["title"], state["waiting"], k)
        leave_key = ("leave", self._hot, k)
        image = self._pixels(key, lambda: banner_image(state["title"], state["waiting"]))
        button = self._pixels(leave_key, lambda: leave_image(self._hot))
        bw, lw = image.width * k, button.width * k
        x = max(8, (int(scene.winfo_width()) - bw - lw - 6 * k) // 2)
        self._place(scene, "banner", key, lambda: self._photo(scene, key, image, k), x, 8, "nw", (BANNER,))
        self._place(scene, "leave", leave_key, lambda: self._photo(scene, leave_key, button, k), x + bw + 6 * k, 8,
                    "nw", (BANNER, LEAVE))
        scene.tag_raise(BANNER)

    def _pixels(self, key: tuple, make):
        found = self._made.get(key)
        if found is None:
            if len(self._made) > 8:
                self._made.clear()
            found = self._made[key] = make()
        return found

    def _hover(self, scene, hot: bool) -> None:
        self._hot = hot
        try:
            scene.config(cursor="hand2" if hot else "")
        except Exception:
            return

    def _leave(self, scene) -> str:
        self._hover(scene, False)
        if self._app is not None:
            focus_mode.leave(self._app)
        return "break"
