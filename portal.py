"""Portal that opens on the surface where two avatars meet.

The clock and the sprite are pure: no window and no tkinter. A meeting
mark says where the pair is going and which meeting phase they are in.
This module turns that into one sprite placement. There is one portal
per meeting, and a self-chat never produces a mark, so it never opens one.

The sprite is 64×48 logical pixels. Point (32, 34) is the surface: the
perch line, or the top edge of the floor. The ellipse is 60×12 and its
centre sits a few pixels below that point, so the ring lies on the
avatars' feet instead of floating above them. Rain rises from the ring.
The same art is used on a perch and on the floor.

``render_portal`` builds the pixels with Pillow. The ring thickness is 1
or 2 logical pixels; the overlay and the preview use 1. Scale is the same
integer factor the avatars' bubbles use (``integer_scale``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from bubbles import integer_scale

SPRITE_W = 64
SPRITE_H = 48
ANCHOR_X = 32
ANCHOR_Y = 34
ELLIPSE_W = 60
ELLIPSE_H = 12
# Vertical centre of the ellipse, in pixels below the surface anchor.
ELLIPSE_BELOW = 4
RISE_MAX = 32
RAIN_SEED = 47211
RAIN_COUNT = 22
LOOP_N = 8
FRAME_MS = 200
RING_PX = 1

# Designer palette. No outer glow, and not the Grok accent.
RING_RGB = (0x7F, 0xDB, 0xFF)
CENTER_RGB = (0xFF, 0xFF, 0xFF)
SHADOW_RGB = (0x1B, 0x2A, 0x4A)
SHADOW_ALPHA = 128  # 50%
SHADOW_DROP = 2

APPEAR = "APPEAR"
LOOP = "LOOP"
DISAPPEAR = "DISAPPEAR"

_OPEN = ("WALK_TO", "MEET", "TALK")


@dataclass(frozen=True)
class PortalSpec:
    """One animation frame, in logical pixels.

    ``rise`` is how high the rain climbs above the ellipse. 0 means the
    rain is off. ``step`` is the rain phase, 0..7, so the loop repeats.
    """

    width: int
    height: int
    rise: int
    step: int


APPEAR_FRAMES = (
    PortalSpec(4, ELLIPSE_H, 0, 0),
    PortalSpec(ELLIPSE_W, ELLIPSE_H, RISE_MAX // 2, 0),
)
LOOP_FRAMES = tuple(
    PortalSpec(ELLIPSE_W, ELLIPSE_H, RISE_MAX, step) for step in range(LOOP_N)
)
# Close is the appear sequence run backwards: rain stops, then the ring shrinks.
DISAPPEAR_FRAMES = (APPEAR_FRAMES[1], APPEAR_FRAMES[0])

FRAMES = {
    APPEAR: APPEAR_FRAMES,
    LOOP: LOOP_FRAMES,
    DISAPPEAR: DISAPPEAR_FRAMES,
}


def frame_catalog():
    """The eight frames in sheet order: appear, loop, disappear."""
    rows = []
    for phase in (APPEAR, LOOP, DISAPPEAR):
        for index, spec in enumerate(FRAMES[phase]):
            rows.append((phase, index, spec))
    return tuple(rows)


def alpha_byte(fraction: float) -> int:
    """Map a 0..1 alpha onto a byte."""
    return int(round(float(fraction) * 255))


@dataclass(frozen=True)
class Drop:
    """One seeded rain drop. ``u`` is 0..1 across the ellipse."""

    u: float
    birth: int
    size: int
    white: bool
    streak: int


def make_drops(count: int = RAIN_COUNT, seed: int = RAIN_SEED) -> tuple:
    """The rain field. The same seed always rebuilds the same drops."""
    rng = random.Random(seed)
    drops = []
    for _ in range(count):
        drops.append(Drop(
            u=rng.uniform(0.06, 0.94),
            birth=rng.randrange(LOOP_N),
            size=1 if rng.random() < 0.6 else 2,
            white=rng.random() < 0.4,
            streak=rng.choice((1, 2, 3)),
        ))
    return tuple(drops)


DROPS = make_drops()


def frame_index(phase: str, elapsed_s: float):
    """Index within ``phase`` at ``elapsed_s``, or None when a clip has ended.

    LOOP wraps. APPEAR and DISAPPEAR are two frames and then None.
    """
    frames = FRAMES.get(phase)
    if not frames:
        return None
    elapsed_ms = int(round(float(elapsed_s) * 1000.0))
    if elapsed_ms < 0:
        elapsed_ms = 0
    index = elapsed_ms // FRAME_MS
    if phase == LOOP:
        return index % len(frames)
    if index >= len(frames):
        return None
    return index


def portal_top_left(surface_x: float, surface_y: float, scale) -> tuple:
    """Top-left so logical point (32, 34) lands on the surface point.

    ``scale`` is the avatar scale. 2.5 draws at 2, the same truncation
    the icon bubbles use.
    """
    factor = integer_scale(scale)
    return (
        float(surface_x) - ANCHOR_X * factor,
        float(surface_y) - ANCHOR_Y * factor,
    )


@dataclass(frozen=True)
class PortalView:
    """One portal to draw this tick. ``surface_*`` is the meeting point."""

    pair: tuple
    phase: str
    index: int
    surface_x: float
    surface_y: float
    spec: PortalSpec


class PortalPlayer:
    """One portal. APPEAR on WALK_TO, LOOP through the talk, DISAPPEAR on the way out.

    ``advance`` takes the current meeting mark or None. RETURN and a missing
    mark (cancel, or the pair was never a meeting) play the close, then nothing.
    A new pair replaces whatever was showing, so two portals are never open.
    """

    def __init__(self):
        self._mode = None
        self._t0_ms = 0
        self._pair = None
        self._x = 0.0
        self._y = 0.0

    def advance(self, mark, now: float):
        now_ms = int(round(float(now) * 1000.0))
        phase = getattr(mark, "phase", None) if mark is not None else None
        open_meeting = phase in _OPEN
        if open_meeting:
            pair = tuple(mark.pair)
            if pair != self._pair or self._mode in (None, DISAPPEAR):
                self._mode = APPEAR
                self._t0_ms = now_ms
                self._pair = pair
            elif self._mode == APPEAR and now_ms - self._t0_ms >= len(APPEAR_FRAMES) * FRAME_MS:
                self._mode = LOOP
                self._t0_ms += len(APPEAR_FRAMES) * FRAME_MS
            self._x = float(mark.x)
            self._y = float(mark.y)
        else:
            if self._mode in (APPEAR, LOOP):
                self._mode = DISAPPEAR
                self._t0_ms = now_ms
            elif self._mode != DISAPPEAR:
                return None
            if mark is not None:
                self._x = float(mark.x)
                self._y = float(mark.y)
            if now_ms - self._t0_ms >= len(DISAPPEAR_FRAMES) * FRAME_MS:
                self._clear()
                return None
        index = frame_index(self._mode, (now_ms - self._t0_ms) / 1000.0)
        if index is None:
            self._clear()
            return None
        return PortalView(
            self._pair,
            self._mode,
            index,
            self._x,
            self._y,
            FRAMES[self._mode][index],
        )

    def _clear(self):
        self._mode = None
        self._pair = None


def _ellipse_fill(width: int, height: int) -> set:
    """Pixels of a filled ellipse in a ``width`` by ``height`` box."""
    filled = set()
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    rx = width / 2.0
    ry = height / 2.0
    for y in range(height):
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            if dx * dx + dy * dy <= 1.0:
                filled.add((x, y))
    return filled


def _ring_pixels(filled: set, thickness: int) -> set:
    """Outline of ``filled``, ``thickness`` pixels inward. 1 or 2."""
    outline = set()
    for x, y in filled:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in filled:
                outline.add((x, y))
                break
    if thickness <= 1:
        return outline
    inner = set()
    rest = filled - outline
    for x, y in rest:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) in outline:
                inner.add((x, y))
                break
    return outline | inner


def _ellipse_origin(width: int, height: int) -> tuple:
    """Top-left of the ellipse box.

    The box is centred on x. Its vertical centre is ``ELLIPSE_BELOW``
    pixels under the surface, so the ring sits on the feet.
    """
    ox = ANCHOR_X - width // 2
    oy = ANCHOR_Y + ELLIPSE_BELOW - height // 2
    return ox, oy


def rain_heads(spec: PortalSpec) -> tuple:
    """Head of each visible drop: ``(x, y, rgb)`` in sprite pixels.

    ``y`` decreases as the drop rises. An empty rise draws nothing.
    The same spec always returns the same heads.
    """
    if spec.rise <= 0:
        return ()
    ox, oy = _ellipse_origin(spec.width, spec.height)
    span = max(1, spec.width - 4)
    heads = []
    for drop in DROPS:
        age = (spec.step - drop.birth) % LOOP_N
        t = (age + 0.15) / float(LOOP_N)
        above = t * spec.rise
        head_x = ox + 2 + int(drop.u * span)
        head_y = oy - int(round(above))
        rgb = CENTER_RGB if drop.white else RING_RGB
        heads.append((head_x, head_y, rgb))
    return tuple(heads)


def _paint(image, x: int, y: int, color) -> None:
    if 0 <= x < SPRITE_W and 0 <= y < SPRITE_H:
        image[x, y] = color


def render_portal(spec: PortalSpec, scale=1, ring: int = RING_PX):
    """RGBA sprite. ``ring`` is 1 or 2 logical pixels. ``scale`` is truncated like the avatars."""
    from PIL import Image

    factor = integer_scale(scale)
    thickness = 2 if int(ring) >= 2 else 1
    image = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    px = image.load()
    filled = _ellipse_fill(spec.width, spec.height)
    ring_px = _ring_pixels(filled, thickness)
    ox, oy = _ellipse_origin(spec.width, spec.height)
    shadow = (*SHADOW_RGB, SHADOW_ALPHA)
    for x, y in filled:
        _paint(px, ox + x, oy + y + SHADOW_DROP, shadow)
    _paint_rain(px, spec, ox, oy)
    white = (*CENTER_RGB, 255)
    cyan = (*RING_RGB, 255)
    for x, y in filled - ring_px:
        _paint(px, ox + x, oy + y, white)
    for x, y in ring_px:
        _paint(px, ox + x, oy + y, cyan)
    if factor != 1:
        image = image.resize(
            (SPRITE_W * factor, SPRITE_H * factor), Image.Resampling.NEAREST)
    return image


def _paint_rain(px, spec: PortalSpec, ox: int, oy: int) -> None:
    """Dots and short streaks rising off the ellipse. Drawn under the ring."""
    if spec.rise <= 0:
        return
    span = max(1, spec.width - 4)
    for drop in DROPS:
        age = (spec.step - drop.birth) % LOOP_N
        t = (age + 0.15) / float(LOOP_N)
        alpha = (1.0 - t) * 0.95
        if alpha < 0.08:
            continue
        head_x = ox + 2 + int(drop.u * span)
        head_y = oy - int(round(t * spec.rise))
        rgb = CENTER_RGB if drop.white else RING_RGB
        for s in range(drop.streak):
            fade = alpha * (1.0 - 0.35 * s)
            byte = alpha_byte(fade)
            if byte <= 0:
                continue
            for dx in range(drop.size):
                for dy in range(drop.size):
                    _paint(px, head_x + dx, head_y + s + dy, (*rgb, byte))


def write_portal_still(path=None):
    """Every frame at 4x. Top row ring 1 px, bottom row ring 2 px."""
    from pathlib import Path
    from PIL import Image, ImageDraw

    directory = Path(__file__).resolve().parent / "docs" / "media"
    target = Path(path) if path else directory / "meet-portal.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    scale = 4
    cell_w = SPRITE_W * scale
    cell_h = SPRITE_H * scale
    gap = 8
    label_w = 56
    catalog = frame_catalog()
    width = label_w + len(catalog) * cell_w + (len(catalog) - 1) * gap + gap
    height = gap + 2 * cell_h + gap + gap
    sheet = Image.new("RGB", (width, height), (22, 22, 31))
    draw = ImageDraw.Draw(sheet)
    for row, (ring, caption) in enumerate(((1, "1 px"), (2, "2 px"))):
        top = gap + row * (cell_h + gap)
        draw.text((8, top + cell_h // 2 - 6), caption, fill=(230, 230, 240))
        for col, (_phase, _index, spec) in enumerate(catalog):
            sprite = render_portal(spec, scale, ring)
            left = label_w + col * (cell_w + gap)
            sheet.paste(sprite, (left, top), sprite)
    sheet.save(target)
    return target
