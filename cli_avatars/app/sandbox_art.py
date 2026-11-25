"""SANDBOX art drawn in code on the Dungeon floor: ember cracks, a rune fence and the warning brazier's glow. No Tk.

``stamp`` paints the still parts into the composed rooms image, under the avatars. ``live_frame`` is the flicker of
the cracks, the runes and the brazier; ``out_frame`` animates a promoted chamber sealed in gold light, and a binned
one dropping through its trapdoor into the dark. Pixels are on the kit's 16x8 iso grid, at 1x.
"""

from __future__ import annotations

import math
import random

import numpy as np

from cli_avatars.app.throne_px import BAYER

KIND = "sandbox"
OUT_S = 1.6
TILE_HALF_W, TILE_HALF_H = 16, 8
STEPS = 10
FLICKER = 6
BG = np.array((0x1A, 0x14, 0x22), np.float32)
CRACK, CRACK_LIT = (12, 8, 14), (122, 42, 16)
POST, POST_HI, POST_LO, RUNE = (90, 78, 102), (122, 110, 136), (43, 36, 51), (255, 179, 71)
EMBER, HOT, GOLD = np.array((255, 106, 42), np.float32), np.array((255, 231, 160), np.float32), \
    np.array((255, 207, 74), np.float32)


def chambers(layout: dict | None) -> list[dict]:
    """The sandbox chambers in a floor layout."""
    return [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("kind") == KIND]


def geometry(chamber: dict) -> dict:
    """Global pixel points of the chamber's cracks, fence posts and brazier flame (before the image origin)."""
    (u0, v0), (w, h) = chamber["origin"], chamber["size"]

    def px(u: float, v: float) -> tuple[float, float]:
        return (u - v) * TILE_HALF_W, (u + v) * TILE_HALF_H

    rng = random.Random(str(chamber.get("sandbox")))
    cu, cv = u0 + 1 + w / 2.0, v0 + 1 + h / 2.0
    cracks = []
    for k in range(4):
        angle = k * math.pi / 2 + rng.uniform(-0.5, 0.5)
        points, (u, v) = [px(cu, cv)], (cu, cv)
        for _ in range(4):
            angle += rng.uniform(-0.6, 0.6)
            u = min(u0 + w - 0.2, max(u0 + 1.2, u + math.cos(angle) * 0.7))
            v = min(v0 + h - 0.2, max(v0 + 1.2, v + math.sin(angle) * 0.7))
            points.append(px(u, v))
        cracks.append(points)
    posts = [px(u0 + w, v0 + 1 + i) for i in range(h)] + [px(u0 + w - i, v0 + h) for i in range(w)]
    return {"cracks": cracks, "posts": posts, "flame": px(u0 + w - 1.5, v0 + 1.5), "center": px(cu, cv)}


def _line(a, b):
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1))
    return [(round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1)]


def crack_pixels(geo: dict) -> list[tuple[int, int]]:
    return [p for points in geo["cracks"] for a, b in zip(points, points[1:], strict=False) for p in _line(a, b)]


def stamp(image, layout: dict | None) -> int:
    """Paint every chamber's cracks and rune fence into ``image``; the count of chambers stamped."""
    left, top = image.info.get("origin", (0, 0))
    found = chambers(layout)
    if not found:
        return 0
    px = image.load()
    width, height = image.size

    def put(x: float, y: float, rgb) -> None:
        x, y = int(x - left), int(y - top)
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = (*rgb, 255)

    for chamber in found:
        geo = geometry(chamber)
        for x, y in crack_pixels(geo):
            put(x, y, CRACK)
            put(x, y + 1, CRACK_LIT)
        posts = geo["posts"]
        for a, b in zip(posts, posts[1:], strict=False):
            for i, (x, y) in enumerate(_line(a, b)):
                if i % 3 == 1:
                    put(x, y - 5, RUNE)
        for x, y in posts:
            for dy in range(9):
                put(x - 1, y - dy, POST_LO)
                put(x, y - dy, POST)
                put(x + 1, y - dy, POST_HI if dy < 8 else POST)
            put(x, y - 9, POST_HI)
            put(x, y - 5, RUNE)
    return len(found)


def live_frame(chamber: dict, step: int):
    """``(RGBA image, (x, y) global px)``: ember cracks, rune pips and the brazier's halo, flicker ``step``."""
    from PIL import Image

    geo = geometry(chamber)
    fx, fy = geo["flame"]
    xs = [p[0] for p in geo["posts"]] + [fx]
    ys = [p[1] for p in geo["posts"]] + [fy]
    x0, y0 = int(min(xs)) - 120, int(min(ys)) - 120
    w, h = int(max(xs)) - x0 + 24, int(max(ys)) - y0 + 24
    out = np.zeros((h, w, 4), np.float32)
    beat = (0.55, 0.8, 1.0, 0.85, 0.65, 0.5)[step % FLICKER]
    yy, xx = np.mgrid[0:h, 0:w]
    dither = np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0
    d = np.hypot((xx + x0 - fx) / 1.6, yy + y0 - (fy - 14))
    halo = np.clip(1.0 - d / (34.0 + 6.0 * beat), 0.0, 1.0) ** 1.5 * beat
    lit = np.floor(halo * 5.0 + dither) / 5.0
    out[..., :3] = EMBER
    out[..., 3] = lit * 120.0
    for x, y in crack_pixels(geo):
        x, y = x - x0, y - y0
        if 0 <= x < w and 0 <= y + 1 < h:
            out[y + 1, x] = (*(EMBER * (0.7 + 0.3 * beat)), 230.0 * beat)
    for x, y in geo["posts"]:
        x, y = int(x - x0), int(y - y0 - 5)
        if 0 <= x < w and 1 <= y < h - 1:
            out[y, x] = (*HOT, 255.0)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                out[y + dy, x + dx] = (*RUNE, 150.0 * beat)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"), (x0, y0)


def out_frame(layers, kind: str, step: int, center: tuple[float, float], at_origin: tuple[int, int]):
    """A promoted (``seal``) or binned (``trapdoor``) chamber ``step`` of ``STEPS`` on its way out, at 1x."""
    from PIL import Image

    plain, behind, mask, (ax, ay) = layers
    t = (step + 1) / STEPS
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w]
    dither = np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16.0
    a = behind[..., 3:4] / 255.0
    dark = behind[..., :3] * a + BG * (1.0 - a)
    cx, cy = center[0] - at_origin[0] - ax, center[1] - at_origin[1] - ay
    d = np.hypot((xx - cx) / 2.0, yy - cy)
    room = plain[..., :3].copy()
    if kind == "seal":
        g = min(1.0, t / 0.45)
        lum = room.mean(axis=2, keepdims=True) / 255.0
        room = room * (1.0 - 0.7 * g) + np.clip(GOLD * (0.35 + 1.1 * lum), 0, 255) * 0.7 * g
        ring = np.abs(d - (1.0 - g) * 60.0 - 8.0) < 2.0
        room = np.where(ring[..., None], HOT, room)
        gone = d / max(1.0, float(d[mask].max()) if mask.any() else 1.0) > 1.0 - max(0.0, (t - 0.45) / 0.55) * 1.1
    else:
        hole = np.clip(t / 0.35, 0.0, 1.0) * 22.0
        pit = (np.abs(xx - cx) / 2.0 + np.abs(yy - cy)) < hole
        fall = max(0.0, (t - 0.35) / 0.65)
        shift = int(fall * 18)
        if shift:
            room = np.concatenate([np.repeat(room[:1], shift, 0), room[:-shift]], 0)
        room = room * (1.0 - 0.7 * fall)
        room = np.where(pit[..., None], np.array((6.0, 4.0, 8.0), np.float32), room)
        gone = (1.0 - yy / max(1, h - 1)) * 0.6 + dither * 0.4 < fall * 1.1 - 0.1
    keep = mask & ~(gone & (dither < 0.95))
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = np.where(keep[..., None], room, dark)
    out[..., 3] = np.where(mask, 255.0, 0.0)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
