"""BACKLOG-BOSS art drawn in code at 1x (no Tk): the pit, the hit flash, the HP bar, the damage number, the chart.

The pit is a round hole in the flagstones with a broken stone lip and an ember glow at the bottom that warms with the
stage. A hit turns the oni white for a blink. The HP bar is an iron frame with a blood-red fill and a gold rim under a
name plate. The burn-down is a parchment sheet: the week's HP per day as a wine-red line over the ideal line to zero.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image

from cli_avatars.app import boss_oni
from cli_avatars.app.courier_art import note
from cli_avatars.app.throne_px import Buf, t35, to_image

STONE, STONE_HI, STONE_LO = (92, 80, 128), (138, 128, 176), (53, 42, 84)
HOLE, HOLE_LO = (22, 16, 34), (8, 6, 14)
EMBER = ((232, 100, 60), (255, 176, 90), (255, 244, 192))
BLOOD, BLOOD_HI, BLOOD_LO = (192, 48, 58), (240, 104, 74), (106, 26, 58)
IRON, IRON_HI = (37, 29, 58), (122, 122, 168)
GOLD, GOLD_LO = (255, 208, 115), (138, 84, 36)
INK, DIM, WINE = (58, 36, 20), (122, 90, 58), (138, 28, 42)
CREAM = (250, 238, 206)
CHART_W, CHART_H = 214, 140


def _hash(x: int, y: int) -> float:
    return ((x * 73856093) ^ (y * 19349663)) % 1000 / 1000.0


@lru_cache(maxsize=16)
def pit(stage: int, glow: int = 0) -> Image.Image:
    """The pit under the oni: an iso ellipse of stone around a dark hole; ``glow`` 0-7 pulses the embers."""
    w = boss_oni.size(stage) + 24
    h = w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = (xx + 0.5 - w / 2) / (w / 2), (yy + 0.5 - h / 2) / (h / 2)
    d = np.sqrt(dx * dx + dy * dy)
    out = np.zeros((h, w, 4), np.uint8)
    heat = (0.25 + 0.12 * stage) * (0.75 + 0.25 * glow / 7)
    for y in range(h):
        for x in range(w):
            r = d[y, x]
            if r > 1:
                continue
            if r > 0.78:
                lit = dx[y, x] > 0.2 and dy[y, x] < 0.3
                col = STONE_HI if lit else STONE_LO if dy[y, x] > 0.4 else STONE
                if _hash(x, y) < 0.12 or (abs(math.atan2(dy[y, x], dx[y, x]) * 5 % 1 - 0.5) < 0.04):
                    col = STONE_LO
            elif r > 0.7:
                col = HOLE_LO
            else:
                depth = 1 - r / 0.7
                ember = depth * heat * (0.6 + 0.4 * (dy[y, x] > 0))
                k = min(2, int(ember * 4))
                col = EMBER[k] if ember > 0.22 and _hash(x, y + glow) < ember else HOLE if r > 0.45 else HOLE_LO
            out[y, x] = (*col, 255)
    return Image.fromarray(out, "RGBA")


@lru_cache(maxsize=32)
def flash(stage: int, f: int, level: int) -> Image.Image:
    """The oni frame bleached toward white by ``level`` 0-4 (a hit lands at 4)."""
    img = np.array(boss_oni.frame(stage, f)).astype(np.float32)
    t = level / 4
    img[..., :3] = img[..., :3] * (1 - t) + 255 * t
    return Image.fromarray(img.astype(np.uint8), "RGBA")


@lru_cache(maxsize=64)
def bar(hp: int, top: int, name: str, hot: bool = False) -> Image.Image:
    """The HP bar: a name plate, then an iron frame with a red fill of ``hp / top`` and the number."""
    width = 76
    b = Buf(width, 22)
    plate = f"{name} HP {hp}"
    pw = len(plate) * 4 + 7
    b.rect((width - pw) // 2, 0, pw, 9, IRON)
    b.rect((width - pw) // 2, 0, pw, 1, GOLD if hot else GOLD_LO)
    t35(b, width // 2, 2, plate, CREAM, align="c", sh=IRON)
    b.rect(0, 11, width, 10, IRON)
    b.rect(1, 12, width - 2, 8, (24, 18, 36))
    fill = 0 if top <= 0 else round((width - 4) * min(1.0, hp / top))
    if fill:
        b.rect(2, 13, fill, 6, BLOOD)
        b.rect(2, 13, fill, 2, BLOOD_HI)
        b.rect(2, 18, fill, 1, BLOOD_LO)
    for x in (0, width - 1):
        b.rect(x, 11, 1, 10, GOLD_LO)
    b.rect(0, 11, width, 1, GOLD if hot else GOLD_LO)
    b.rect(0, 20, width, 1, GOLD_LO)
    return to_image(b)


@lru_cache(maxsize=16)
def damage(text: str) -> Image.Image:
    """A damage number: big blocky digits in hot red with an ink shadow."""
    b = Buf(len(text) * 8 + 4, 14)
    t35(b, 2, 2, text, BLOOD_HI, sh=IRON, k=2)
    return to_image(b)


@lru_cache(maxsize=8)
def button(hot: bool = False) -> Image.Image:
    """The burn-down toggle: a small rolled scroll with a red line on it."""
    b = Buf(18, 14)
    b.rect(2, 3, 14, 8, (236, 222, 184))
    b.rect(0, 2, 2, 10, (184, 160, 116))
    b.rect(16, 2, 2, 10, (184, 160, 116))
    for x, y in ((4, 8), (6, 7), (8, 7), (10, 6), (12, 5), (14, 4)):
        b.rect(x, y, 2, 1, WINE if not hot else BLOOD_HI)
    return to_image(b)


def _points(week: tuple, x0: int, y0: int, w: int, h: int, top: int) -> list[tuple[int, int] | None]:
    step = w / max(1, len(week) - 1)
    return [None if v is None else (round(x0 + i * step), round(y0 + h - h * v / max(1, top)))
            for i, v in enumerate(week)]


@lru_cache(maxsize=16)
def chart(week: tuple, days: tuple, title: str) -> Image.Image:
    """The burn-down parchment: ``week`` is HP per weekday (None for days to come), ``days`` the labels."""
    image = note(CHART_W, CHART_H)
    b = Buf(CHART_W, CHART_H)
    x0, y0, w, h = 30, 34, CHART_W - 76, CHART_H - 72
    t35(b, CHART_W // 2, 14, title, WINE, align="c", k=1)
    top = max([1] + [v for v in week if v is not None])
    b.rect(x0 - 2, y0, 1, h + 1, INK)
    b.rect(x0 - 2, y0 + h, w + 6, 1, INK)
    for k in range(5):
        y = y0 + round(h * k / 4)
        b.rect(x0 - 4, y, 2, 1, INK)
        t35(b, x0 - 7, y - 2, round(top * (4 - k) / 4), DIM, align="r")
        for x in range(x0, x0 + w + 2, 4):
            b.px(x, y, DIM, 0.35)
    first = next((v for v in week if v is not None), None)
    if first:
        for i in range(0, w, 3):
            b.px(x0 + i, round(y0 + h - h * first / top * (1 - i / w)), DIM, 0.8)
    pts = _points(week, x0, y0, w, h, top)
    for p, q in zip(pts, pts[1:], strict=False):
        if p and q:
            for dy in (0, 1):
                b.line(p[0], p[1] + dy, q[0], q[1] + dy, WINE)
    for i, p in enumerate(pts):
        x = round(x0 + i * w / max(1, len(week) - 1))
        t35(b, x, y0 + h + 6, days[i], INK, align="c")
        if p is None:
            continue
        b.rect(p[0] - 2, p[1] - 2, 5, 5, BLOOD_LO)
        b.rect(p[0] - 1, p[1] - 1, 3, 3, BLOOD_HI)
        t35(b, p[0], p[1] - 9, week[i], INK, align="c")
    image.alpha_composite(to_image(b))
    return image
