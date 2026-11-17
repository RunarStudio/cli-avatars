"""Portal that opens on the surface where two avatars meet.

The clock and the sprite are pure: no window and no tkinter. A meeting
mark says where the pair is going and which meeting phase they are in.
This module turns that into one sprite placement. There is one portal
per meeting, and a self-chat never produces a mark, so it never opens one.

The sprite is 40x40 logical pixels. Point (20, 36) sits on the surface:
the perch line, or the top edge of the floor. The same art is used for both.
``render_portal`` builds the pixels with Pillow. The ring thickness is 1 or
2 logical pixels; the overlay and the preview use 1. Scale is the same
integer factor the avatars' bubbles use (``integer_scale``).
"""

from __future__ import annotations

from dataclasses import dataclass

from bubbles import integer_scale

SPRITE = 40
ANCHOR_X = 20
ANCHOR_Y = 36
BEAM_W = 10
BEAM_MAX = 28
ELLIPSE_W = 40
ELLIPSE_H = 12
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

    ``alpha`` is the bottom band of the beam (0.60 or 0.45). The middle
    band is half of that and the top band is 0.
    """

    width: int
    height: int
    beam: int
    alpha: float


APPEAR_FRAMES = (
    PortalSpec(4, ELLIPSE_H, 0, 0.60),
    PortalSpec(ELLIPSE_W, ELLIPSE_H, BEAM_MAX, 0.60),
)
LOOP_FRAMES = (
    PortalSpec(ELLIPSE_W, ELLIPSE_H + 1, BEAM_MAX, 0.60),
    PortalSpec(ELLIPSE_W, ELLIPSE_H - 1, BEAM_MAX, 0.45),
    PortalSpec(ELLIPSE_W, ELLIPSE_H + 1, BEAM_MAX, 0.60),
    PortalSpec(ELLIPSE_W, ELLIPSE_H - 1, BEAM_MAX, 0.45),
)
# Close is the appear sequence run backwards.
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
    """Map a 0..1 alpha onto a byte. 60% is 153 and 30% is 76."""
    return int(round(float(fraction) * 255))


def beam_bands(height: int, base_alpha: float) -> tuple:
    """Three bands, bottom to top: ``base``, half, then 0.

    Returns ``((row_count, alpha_byte), ...)``. A zero-height beam has
    no bands. The top band is present and fully transparent.
    """
    if height <= 0:
        return ()
    third = height // 3
    counts = (third, third, height - 2 * third)
    levels = (base_alpha, base_alpha / 2.0, 0.0)
    return tuple((count, alpha_byte(level)) for count, level in zip(counts, levels))


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
    """Top-left so logical point (20, 36) lands on the surface point.

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
    """Top-left of the ellipse box. Its bottom-center is the anchor."""
    return (ANCHOR_X - width // 2, ANCHOR_Y - height + 1)


def _paint(image, x: int, y: int, color) -> None:
    if 0 <= x < SPRITE and 0 <= y < SPRITE:
        image[x, y] = color


def render_portal(spec: PortalSpec, scale=1, ring: int = RING_PX):
    """RGBA sprite. ``ring`` is 1 or 2 logical pixels. ``scale`` is truncated like the avatars."""
    from PIL import Image

    factor = integer_scale(scale)
    thickness = 2 if int(ring) >= 2 else 1
    image = Image.new("RGBA", (SPRITE, SPRITE), (0, 0, 0, 0))
    px = image.load()
    filled = _ellipse_fill(spec.width, spec.height)
    ring_px = _ring_pixels(filled, thickness)
    ox, oy = _ellipse_origin(spec.width, spec.height)
    shadow = (*SHADOW_RGB, SHADOW_ALPHA)
    for x, y in filled:
        _paint(px, ox + x, oy + y + SHADOW_DROP, shadow)
    _paint_beam(px, spec, oy)
    white = (*CENTER_RGB, 255)
    cyan = (*RING_RGB, 255)
    for x, y in filled - ring_px:
        _paint(px, ox + x, oy + y, white)
    for x, y in ring_px:
        _paint(px, ox + x, oy + y, cyan)
    if factor != 1:
        image = image.resize((SPRITE * factor, SPRITE * factor), Image.Resampling.NEAREST)
    return image


def _paint_beam(px, spec: PortalSpec, ellipse_top: int) -> None:
    """10 px column standing on the ellipse. Three alpha bands, bottom to top."""
    if spec.beam <= 0:
        return
    left = ANCHOR_X - BEAM_W // 2
    bottom = ellipse_top - 1
    bands = beam_bands(spec.beam, spec.alpha)
    row = 0
    for count, alpha in bands:
        for _ in range(count):
            y = bottom - row
            row += 1
            if alpha == 0:
                continue
            color = (*RING_RGB, alpha)
            for x in range(left, left + BEAM_W):
                _paint(px, x, y, color)


def write_portal_still(path=None):
    """All 8 frames at 4x. Top row ring 1 px, bottom row ring 2 px."""
    from pathlib import Path
    from PIL import Image, ImageDraw

    directory = Path(__file__).resolve().parent / "docs" / "media"
    target = Path(path) if path else directory / "meet-portal.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    scale = 4
    cell = SPRITE * scale
    gap = 8
    label_w = 56
    catalog = frame_catalog()
    width = label_w + len(catalog) * cell + (len(catalog) - 1) * gap + gap
    height = gap + 2 * cell + gap + gap
    sheet = Image.new("RGB", (width, height), (22, 22, 31))
    draw = ImageDraw.Draw(sheet)
    for row, (ring, caption) in enumerate(((1, "1 px"), (2, "2 px"))):
        top = gap + row * (cell + gap)
        draw.text((8, top + cell // 2 - 6), caption, fill=(230, 230, 240))
        for col, (_phase, _index, spec) in enumerate(catalog):
            sprite = render_portal(spec, scale, ring)
            left = label_w + col * (cell + gap)
            sheet.paste(sprite, (left, top), sprite)
    sheet.save(target)
    return target
