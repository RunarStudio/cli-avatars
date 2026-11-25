"""SELECT-LIGHT.1: a selected room's light rises from its floor like rain falling upwards, then holds as its glow.

``RoomGlow.paint`` calls ``rise_for(glow).paint`` each frame. A new selection (a Topics row click or a grabbed
avatar) sends a burst of small warm drops up from random spots of the room's floor to about wall height while the
torchlight ramps up under them, then a sparse loop while the light holds; a deselect stops spawning and the drops
fade with the glow. Drop sprites are drawn in code once per look and scale; canvas items are a pool moved in place.
``config.json`` ``room_glow.drops: false`` turns them off; they and their ``shimmer`` cue wait while a task is in focus.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from cli_avatars.app import cues, focus_mode
from cli_avatars.app.room_floor import Plan
from cli_avatars.app.throne_px import BAYER

TAG = "room-rise"
GLOW_TAG = "room-glow"
MAX_DROPS = 48
BURST_S, BURST_RATE, SPARSE_RATE = 0.6, 80.0, 9.0
LIFE_S = (0.75, 1.3)
RISE_PX = (28.0, 56.0)
SPARK_S = 0.12
LEVELS = 4
KINDS = ("spark", "drop", "long", "wide")
CUE_GAP_S = 1.0
HOT, GOLD, EMBER, DEEP = (255, 250, 214), (255, 214, 120), (242, 163, 58), (176, 84, 18)
RATE = 22050


def rise_for(glow) -> RisingLight:
    found = getattr(glow, "_rise", None)
    if found is None:
        found = glow._rise = RisingLight()
    return found


def enabled(config: object) -> bool:
    section = config.get("room_glow") if isinstance(config, dict) else None
    return not (isinstance(section, dict) and section.get("drops") is False)


@dataclass(frozen=True)
class Drop:
    t0: float
    u: float
    v: float
    rise: float
    life: float
    kind: str


class RisingLight:
    """The drops of the selected room: spawned by ``step``, drawn by ``paint`` as pooled canvas images."""

    def __init__(self) -> None:
        self.room: str | None = None
        self.drops: list[Drop] = []
        self.spawned = 0
        self._start = None
        self._last: float | None = None
        self._owed = 0.0
        self._rng = random.Random(0x5EED)
        self._cue_at = -1e9
        self._plan: tuple = (None, None)
        self._items: list[int] = []
        self._keys: list[tuple | None] = []
        self._photos: dict[tuple, object] = {}

    def height(self, drop: Drop, now: float) -> float:
        """Base pixels above the floor: quick off the floor, easing near the top."""
        t = min(1.0, max(0.0, (now - drop.t0) / drop.life))
        return drop.rise * t * (1.5 - 0.5 * t)

    def alpha(self, drop: Drop, now: float, fade: float) -> float:
        t = min(1.0, max(0.0, (now - drop.t0) / drop.life))
        return max(0.0, min(1.0, 0.6 + t / 0.2) * min(1.0, (1.0 - t) / 0.45) * fade)

    def step(self, glow, floor, now: float) -> bool:
        """Age, drop and spawn for ``now``; True when a new selection starts its burst."""
        room = glow.room if floor is not None else None
        if room != self.room:
            self.room, self.drops, self._start = room, [], None
        dt = 0.0 if self._last is None else min(0.25, max(0.0, now - self._last))
        self._last = now
        if room is None:
            return False
        self.drops = [d for d in self.drops if now - d.t0 < d.life]
        started = glow._on and glow._t0 != self._start
        if started:
            self._start, self._owed = glow._t0, 1.0
        if glow._on:
            self._owed = min(2.0, self._owed + dt * (BURST_RATE if now - self._start < BURST_S else SPARSE_RATE))
            while self._owed >= 1.0 and len(self.drops) < MAX_DROPS:
                self._owed -= 1.0
                self._spawn(floor, now)
        return started

    def _spawn(self, floor, now: float) -> None:
        a, b, c, d = floor.box()
        rng = self._rng
        kind = rng.choice(("drop", "drop", "long", "wide"))
        self.drops.append(Drop(now, rng.uniform(a, c), rng.uniform(b, d), rng.uniform(*RISE_PX), rng.uniform(*LIFE_S),
                               kind))
        self.spawned += 1

    def paint(self, scene, painter, app, glow, now: float) -> None:
        on = painter is not None and painter._scale and scene.winfo_exists() and enabled(getattr(app, "config", None))
        on = on and not focus_mode.state(app)["task"]
        floor = self._floor(painter, glow.room) if on and glow.room else None
        if self.step(glow, floor, now) and now - self._cue_at >= CUE_GAP_S:
            self._cue_at = now
            cues.play(app, "shimmer")
        if not self.drops:
            self._hide(scene, 0)
            return
        s = painter._scale
        corner = painter._corner()
        fade = 1.0 if glow._on else glow.level(now)
        shown = []
        for drop in self.drops:
            level = math.ceil(self.alpha(drop, now, fade) * LEVELS)
            at = painter.to_canvas(drop.u, drop.v)
            if level <= 0 or at is None or corner is None:
                continue
            x = corner[0] + round((at[0] - corner[0]) / s) * s
            y = corner[1] + round((at[1] - corner[1] - self.height(drop, now) * s) / s) * s
            shown.append((x, y, ("spark" if now - drop.t0 < SPARK_S else drop.kind, level, s)))
        self._draw(scene, shown)

    def clear(self, scene) -> None:
        if self._items:
            for item in self._items:
                scene.delete(item)
            self._items, self._keys = [], []
        self.room, self.drops, self._start = None, [], None

    def _floor(self, painter, room: str):
        layout = painter.layout
        if self._plan[0] is not layout:
            self._plan = (layout, Plan.from_layout(layout))
        return self._plan[1].floor(room)

    def _draw(self, scene, shown: list) -> None:
        if self._items and not scene.find_withtag(self._items[0]):
            self._items, self._keys = [], []
        for i, (x, y, key) in enumerate(shown):
            photo = self._photos.get(key)
            if photo is None:
                photo = self._photos[key] = sprite(scene, key)
            if i >= len(self._items):
                self._items.append(scene.create_image(x, y, image=photo, anchor="s", tags=("floor", TAG)))
                self._keys.append(key)
                continue
            item = self._items[i]
            if self._keys[i] != key:
                scene.itemconfigure(item, image=photo, state="normal")
                self._keys[i] = key
            scene.coords(item, x, y)
        self._hide(scene, len(shown))
        try:
            scene.tag_raise(TAG, GLOW_TAG)
        except Exception:
            pass

    def _hide(self, scene, start: int) -> None:
        for i in range(start, len(self._items)):
            if self._keys[i] is not None:
                scene.itemconfigure(self._items[i], state="hidden")
                self._keys[i] = None


def sprite(scene, key: tuple):
    """Tk image for ``(kind, level, scale)``."""
    from PIL import Image, ImageTk

    kind, level, scale = key
    art = drop_art(kind, level)
    if scale > 1:
        art = art.resize((art.width * scale, art.height * scale), Image.NEAREST)
    return ImageTk.PhotoImage(art, master=scene)


def drop_art(kind: str, level: int):
    """A drop at 1x: a white-hot head over a warm tail that thins out in a dither; ``spark`` is the floor glint."""
    from PIL import Image

    if kind == "spark":
        out = np.zeros((3, 5, 4), np.float32)
        out[0, 1:4] = ((*EMBER, 150), (*HOT, 255), (*EMBER, 150))
        out[1] = ((*EMBER, 90), (*GOLD, 220), (*HOT, 255), (*GOLD, 220), (*EMBER, 90))
        out[2, 1:4] = ((*EMBER, 150), (*GOLD, 200), (*EMBER, 150))
    else:
        n, w = {"drop": (10, 1), "long": (15, 1), "wide": (12, 3)}[kind]
        out = np.zeros((n, w, 4), np.float32)
        mid = w // 2
        ramp = np.array((HOT, GOLD, EMBER, DEEP), np.float32)
        for i in range(n):
            f = 1.0 - max(0, i - 1) / n
            pos = min(2.999, (1.0 - f) * 3.0)
            k = int(pos)
            rgb = ramp[k] + (ramp[k + 1] - ramp[k]) * (pos - k)
            if i >= 2 and f * 17.0 < BAYER[(i & 3) * 4 + (mid & 3)] + 1:
                continue
            out[i, mid] = (*rgb, 255.0 * f ** 0.7)
        if w == 3:
            for i in range(5):
                out[i, 0] = out[i, 2] = (*GOLD, 120.0 - 24.0 * i)
    out[..., 3] *= max(0, min(LEVELS, level)) / LEVELS
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def shimmer() -> np.ndarray:
    """A soft shimmer: glassy pings rising up a pentatonic run over a faint airy swell, like drops of light."""
    n = int(RATE * 0.95)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(83)
    air = np.convolve(rng.standard_normal(n), np.ones(5) / 5, "same") * np.sin(np.pi * t / t[-1]) ** 2 * 0.05
    out = air.astype(np.float32)
    for i, pitch in enumerate((1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0)):
        m = int(RATE * 0.4)
        tt = np.arange(m) / RATE
        ping = (np.sin(2 * np.pi * pitch * tt) + 0.25 * np.sin(2 * np.pi * pitch * 2.76 * tt)) * np.exp(-tt * 11)
        start = int(RATE * (0.03 + i * 0.085))
        out[start:start + m] += (ping * np.minimum(1.0, tt / 0.004) * (0.55 - 0.05 * i))[:n - start].astype(np.float32)
    return out
