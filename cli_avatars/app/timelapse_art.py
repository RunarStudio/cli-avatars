"""TIMELAPSE art, drawn in code at 1x (no Tk): the sundial bar, the sand-glass playhead, the map tinted to the hour,
ghost underglows and trail motes, and the avatars' roster frames (docs/time-lapse.md)."""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from cli_avatars.app.throne_model import GOLD, WINE, label
from cli_avatars.app.throne_px import BAYER, Buf, t35, to_image, tone

BAR_H = 34
TRACK_X0 = 34
TRACK_RIGHT = 72
BAND_Y, BAND_H = 18, 7
STONE, STONE_LO, STONE_HI, INK, DIM = "#2a2236", "#120d1a", "#4e4262", "#f0e6c8", "#8a8098"
# minute of the day -> sky colour; the map is tinted towards it, darker at night
SKY = ((0, (14, 16, 44)), (300, (22, 22, 62)), (360, (150, 80, 120)), (420, (236, 160, 110)), (540, (150, 186, 222)),
       (1020, (156, 182, 214)), (1110, (238, 140, 70)), (1170, (128, 60, 112)), (1260, (24, 20, 58)),
       (1440, (14, 16, 44)))
LIGHT = ((0, 0.34), (330, 0.38), (420, 0.74), (540, 1.0), (1020, 1.0), (1140, 0.7), (1260, 0.38), (1440, 0.34))
# minute -> colour cast of the light: moonlit blue, rose dawn, warm noon, amber dusk
CAST = ((0, (0.5, 0.6, 1.0)), (330, (0.55, 0.6, 1.0)), (390, (1.0, 0.7, 0.74)), (450, (1.0, 0.88, 0.76)),
        (540, (1.0, 0.98, 0.93)), (1020, (1.0, 0.96, 0.88)), (1110, (1.0, 0.7, 0.46)), (1190, (0.78, 0.56, 0.86)),
        (1260, (0.5, 0.6, 1.0)), (1440, (0.5, 0.6, 1.0)))
GLOW = {"user": "#ffd27a", "orchestrator": "#b48cff", "grok": "#7fe0c0"}


def _lerp(keys, minute: float):
    minute = min(max(minute, 0.0), 1440.0)
    for (m0, a), (m1, b) in zip(keys, keys[1:], strict=False):
        if m0 <= minute <= m1:
            t = (minute - m0) / max(1e-6, m1 - m0)
            if isinstance(a, tuple):
                return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))
            return a + (b - a) * t
    return keys[-1][1]


def sky(minute: float) -> tuple[int, int, int]:
    return tuple(int(round(v)) for v in _lerp(SKY, minute))


def light(minute: float) -> float:
    return _lerp(LIGHT, minute)


def tint(base, minute: float):
    """The composed map at the hour: dimmed towards the sky's colour, dithered in steps; torch fire stays lit."""
    from PIL import Image

    from cli_avatars.app.focus_veil import flames

    rgba = np.asarray(base, dtype=np.float32)
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    dither = np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0
    k = (np.floor(light(minute) * 10.0 + dither * 0.9) / 10.0)[..., None]
    rgb = rgba[..., :3]
    cast = np.array(_lerp(CAST, minute), np.float32)
    out = rgb * k * cast + np.array(sky(minute), np.float32) * (1.0 - k) * 0.4
    fire = flames(rgb)[..., None]
    out = np.where(fire, np.minimum(255.0, rgb * (1.0 + (1.0 - k) * 0.5)), out)
    full = np.concatenate([np.clip(out, 0, 255), rgba[..., 3:]], axis=-1)
    return Image.fromarray(full.astype(np.uint8), "RGBA")


def track_x(minute: float, width: int) -> float:
    """1x x of a minute on a bar ``width`` wide."""
    return TRACK_X0 + (width - TRACK_X0 - TRACK_RIGHT) * min(max(minute, 0.0), 1440.0) / 1440.0


def minute_at(x: float, width: int) -> float:
    span = width - TRACK_X0 - TRACK_RIGHT
    return min(max((x - TRACK_X0) / max(1, span) * 1440.0, 0.0), 1439.0)


def bar(width: int, title: str, moments: list[int], busy: list[int], now: float | None, first: bool,
        last: bool):
    """The stone bar at 1x: day title with arrows, the sky band over 24 hours with stars, sun and hour ticks,
    activity runes under it, a wine gem per chat moment, the dark future past ``now``, and LEAVE."""
    b = Buf(width, BAR_H)
    b.rect(0, 1, width, BAR_H - 1, STONE_LO)
    b.rect(0, 0, width, BAR_H - 1, tone(GOLD, 0.5))
    b.rect(1, 1, width - 2, BAR_H - 3, STONE)
    b.rect(1, 1, width - 2, 1, STONE_HI)
    for x in range(3, width - 3, 7):
        b.px(x, BAR_H - 4, STONE_LO)
    for x, y in ((0, 0), (width - 1, 0), (0, BAR_H - 2), (width - 1, BAR_H - 2)):
        b.px(x, y, GOLD)
    x0, x1 = TRACK_X0, width - TRACK_RIGHT
    _arrow(b, x0, 4, -1, DIM if first else GOLD)
    t35(b, x0 + 6, 4, label(title, 40), INK, sh="#08060c")
    _arrow(b, x0 + 10 + len(label(title, 40)) * 4, 4, 1, DIM if last else GOLD)
    b.rect(x0 - 1, BAND_Y - 1, x1 - x0 + 2, BAND_H + 2, STONE_LO)
    for x in range(x0, x1):
        minute = minute_at(x + 0.5, width)
        c = sky(minute)
        for y in range(BAND_H):
            shade = 0.82 + 0.3 * (1 - y / BAND_H)
            b.px(x, BAND_Y + y, tuple(min(255, int(v * shade)) for v in c))
        if light(minute) < 0.5 and (x * 7919) % 23 == 0:
            b.px(x, BAND_Y + 1 + (x * 31) % 4, "#fff4d6")
    noon = int(track_x(780, width))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy <= 5:
                b.px(noon + dx, BAND_Y + 3 + dy, "#ffe9a0" if dx * dx + dy * dy <= 2 else "#ffc050")
    for hour in range(0, 25, 3):
        x = int(track_x(hour * 60, width))
        b.rect(x, BAND_Y + BAND_H + 1, 1, 2, tone(GOLD, 0.8))
        if hour % 6 == 0 and hour < 24:
            t35(b, x + 2, BAND_Y + BAND_H + 1, f"{hour:02d}", DIM)
    if busy:
        top = max(busy)
        for i, n in enumerate(busy):
            if n:
                h = 1 + round(3 * n / top)
                xa = int(track_x(i * 1440 / len(busy), width))
                xb = int(track_x((i + 1) * 1440 / len(busy), width))
                b.rect(xa, BAND_Y + BAND_H - h, max(1, xb - xa - 1), h, "#e0aa3e", 0.55)
    if now is not None:
        xn = int(track_x(now, width))
        b.rect(xn + 1, BAND_Y, x1 - xn - 1, BAND_H, "#06040b", 0.62)
        b.rect(xn, BAND_Y - 2, 1, BAND_H + 4, "#ff6a5a")
    for minute in moments:
        x = int(track_x(minute, width))
        for dy, half in ((0, 0), (1, 1), (2, 2), (3, 1), (4, 0)):
            b.rect(x - half, 10 + dy, half * 2 + 1, 1, WINE if dy else "#ff9aa0")
        b.px(x, 11, "#ffd0d4")
    lx = width - 30
    b.rect(lx, 4, 26, 11, tone("#7a2436", 0.6))
    b.rect(lx + 1, 4, 24, 10, "#7a2436")
    t35(b, lx + 3, 7, "LEAVE", INK, sh="#3a0c18")
    return to_image(b)


def _arrow(b: Buf, x: int, y: int, way: int, c) -> None:
    """A 3x5 pointer: left for ``way`` -1, right for 1."""
    for i, h in enumerate((1, 3, 5) if way < 0 else (5, 3, 1)):
        b.rect(x + i, y + (5 - h) // 2 + 1, 1, h, "#08060c")
        b.rect(x + i, y + (5 - h) // 2, 1, h, c)


def leave_box(width: int) -> tuple[int, int, int, int]:
    return width - 30, 4, width - 4, 15


def play_box(width: int) -> tuple[int, int, int, int]:
    return width - 66, 4, width - 53, 15


def speed_box(width: int) -> tuple[int, int, int, int]:
    return width - 50, 4, width - 33, 15


def arrows(title: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """1x x spans of the ◄ and ► beside the title."""
    end = TRACK_X0 + 10 + len(label(title, 40)) * 4
    return (TRACK_X0 - 2, TRACK_X0 + 5), (end - 2, end + 5)


@lru_cache(maxsize=8)
def button(kind: str, hot: bool = False):
    """Play, pause, or a speed plate (``x1``/``x4``/``x16``)."""
    width = 14 if kind in ("play", "pause") else 18
    b = Buf(width, 12)
    face = "#e0a83c" if hot else "#3a2f4e"
    b.rect(0, 0, width, 12, tone(face, 0.6))
    b.rect(1, 0, width - 2, 11, face)
    b.rect(1, 0, width - 2, 1, tone(face, 1.3))
    ink = "#1a1226" if hot else INK
    if kind == "play":
        for i in range(7):
            b.rect(5, 2 + i, 1 + min(i, 6 - i), 1, ink)
    elif kind == "pause":
        b.rect(4, 2, 2, 7, ink)
        b.rect(8, 2, 2, 7, ink)
    else:
        t35(b, width // 2, 3, kind.upper(), ink, align="c")
    return to_image(b)


@lru_cache(maxsize=24)
def sundial(step: int):
    """A bronze sundial seen from above; the gnomon's shadow points to the hour (``step`` of 48 a day)."""
    b = Buf(28, 28)
    cx = cy = 13.5
    for y in range(28):
        for x in range(28):
            d = math.hypot(x - cx, y - cy)
            if d <= 13:
                rim = d > 11.2
                c = "#6a4a22" if rim else ("#c9a462" if (x + y) % 2 else "#c09a58")
                b.px(x, y, tone(c, 1.0 - 0.18 * (y - cy) / 13))
    for hour in range(12):
        a = hour / 12 * 2 * math.pi - math.pi / 2
        b.px(round(cx + math.cos(a) * 9.6), round(cy + math.sin(a) * 9.6), "#3a2410")
    minute = step * 30
    a = (minute / 1440) * 2 * math.pi + math.pi / 2
    lit = light(minute) > 0.5
    for r in np.arange(0.0, 9.5, 0.5):
        b.px(round(cx + math.cos(a) * r), round(cy + math.sin(a) * r), "#2a1808" if lit else "#4a3a5a",
             0.85 if lit else 0.5)
    b.rect(13, 13, 2, 2, GOLD)
    b.px(13, 12, "#fff0b0")
    return to_image(b)


@lru_cache(maxsize=8)
def glass(frame: int):
    """The sand-glass playhead, 9x16: sand runs down in four frames."""
    b = Buf(9, 16)
    b.rect(0, 0, 9, 2, "#6a4a22")
    b.rect(0, 14, 9, 2, "#6a4a22")
    b.rect(0, 0, 9, 1, GOLD)
    for y in range(2, 14):
        half = max(1, round(abs(y - 7.5) * 0.55 + 0.5))
        b.rect(4 - half, y, half * 2 + 1, 1, "#9ad0e0", 0.45)
    top = 3 + frame
    for y in range(top, 7):
        half = max(0, round(abs(y - 7.5) * 0.55 - 0.3))
        b.rect(4 - half, y, half * 2 + 1, 1, "#f0c870")
    for y in range(13 - frame, 14):
        half = max(0, round(abs(y - 7.5) * 0.55 - 0.3))
        b.rect(4 - half, y, half * 2 + 1, 1, "#e0aa3e")
    b.px(4, 8 + frame % 3, "#ffe6a0")
    return to_image(b)


@lru_cache(maxsize=4)
def entry(hot: bool = False):
    """The TIME-LAPSE plate shown on the floor while the live view runs."""
    text = "TIME-LAPSE"
    width = len(text) * 4 + 18
    b = Buf(width, 15)
    face = "#e0a83c" if hot else "#2a2236"
    b.rect(0, 1, width, 14, STONE_LO)
    b.rect(0, 0, width, 14, tone(GOLD, 0.55))
    b.rect(1, 1, width - 2, 12, face)
    t35(b, 13, 5, text, "#1a1226" if hot else INK, sh=None if hot else "#08060c")
    out = to_image(b)
    out.alpha_composite(glass(1).resize((7, 12)), (3, 1))
    return out


@lru_cache(maxsize=16)
def underglow(kind: str, size: int):
    """A soft oval of the avatar's colour under its feet, ``size`` px wide."""
    from PIL import Image

    w, h = size, max(4, size // 3)
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot((xx - (w - 1) / 2) / (w / 2), (yy - (h - 1) / 2) / (h / 2))
    a = np.clip(1.0 - d, 0.0, 1.0) ** 1.4 * 150
    rgb = np.array(_rgb(GLOW.get(kind, GOLD)), np.float32)
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = rgb
    out[..., 3] = a
    return Image.fromarray(out.astype(np.uint8), "RGBA")


@lru_cache(maxsize=24)
def mote(kind: str, level: int, scale: int):
    """One trail mote, a small ghost diamond; ``level`` 1..4 is how bright."""
    from PIL import Image

    side = 5 * scale
    out = np.zeros((side, side, 4), np.uint8)
    c = np.array(_rgb(GLOW.get(kind, GOLD)), np.float32)
    mid = (side - 1) / 2
    for y in range(side):
        for x in range(side):
            d = (abs(x - mid) + abs(y - mid)) / (side / 2)
            if d <= 1.0:
                core = d < 0.4
                rgb = c + (255 - c) * 0.6 if core else c
                out[y, x] = (*rgb.astype(np.uint8), int((60 + 48 * level) * (1.0 if core else 0.55)))
    return Image.fromarray(out, "RGBA")


@lru_cache(maxsize=32)
def tag(name: str, kind: str):
    """A small name plate under a ghost."""
    text = label(name, 14) or "?"
    width = len(text) * 4 + 5
    b = Buf(width, 9)
    b.rect(0, 0, width, 9, "#0c0812", 0.82)
    b.rect(0, 8, width, 1, GLOW.get(kind, GOLD), 0.8)
    t35(b, 3, 2, text, GLOW.get(kind, GOLD) if kind == "user" else INK)
    return to_image(b)


@lru_cache(maxsize=12)
def frames(kind: str) -> tuple[tuple, tuple]:
    """``(idle, walk)`` roster frames of a kind at native size, as the Dungeon crops them."""
    from PIL import Image

    from bundle_paths import asset_path
    from cli_avatars.app.av_roster import LOOKS

    look = LOOKS.get(kind, LOOKS["orchestrator"])
    try:
        with Image.open(asset_path("Sprites", f"{look.skin}.png")) as img:
            sheet = img.convert("RGBA")
    except (OSError, ValueError):
        return (), ()
    rows = []
    for row in (0, 1):
        cells = []
        for col in range(sheet.width // look.cell):
            x, y = col * look.cell + look.dx, row * look.cell + look.dy
            cell = sheet.crop((x, y, x + look.size, y + look.size))
            if cell.getchannel("A").getbbox() is None:
                break
            cells.append(cell)
        rows.append(tuple(cells) or (rows[0] if rows else ()))
    return rows[0], rows[1]


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
