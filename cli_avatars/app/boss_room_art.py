"""BOSS-ROOM.1 art drawn in code at 1x (no Tk): the pit that widens with the room, the Crypt's niches and skulls,
its carved count plaque, and the dust a moving wall throws up.

The pit is an iso ellipse of broken stone around a dark hole with embers at the bottom; its width follows the room.
A niche is a dark arched recess sheared onto a back wall (``"r"`` the back row, ``"l"`` the back column); a skull
is ivory with ink sockets and teeth and sits in one. The plaque is a slab of carved stone; its words are written at
full size in the chosen face (``art_words``), after the 1x slab is scaled.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from cli_avatars.app.boss_art import EMBER, HOLE, HOLE_LO, STONE, STONE_HI, STONE_LO
from cli_avatars.app.throne_px import Buf, to_image

BONE, BONE_HI, BONE_LO, SOCKET = (226, 214, 184), (250, 244, 224), (150, 132, 104), (34, 22, 30)
RECESS, RECESS_LO, RIM = (30, 22, 40), (14, 10, 20), (118, 106, 150)
SLAB, SLAB_HI, SLAB_LO, CARVE = (96, 88, 112), (142, 134, 160), (52, 46, 66), (232, 220, 196)
DUST = (206, 190, 160)
SKULL_W, SKULL_H = 7, 7
NICHE_W, NICHE_H = 9, 10
PUFF_FRAMES = 6


def _noise(w: int, h: int, seed: int) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    return ((x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)) % 1000 / 1000.0


@lru_cache(maxsize=24)
def pit(width: int, stage: int, glow: int = 0) -> Image.Image:
    """The pit, ``width`` px across (half as tall): a stone lip, a dark hole, embers that warm with the stage."""
    w = max(8, int(width)) // 2 * 2
    h = w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = (xx + 0.5 - w / 2) / (w / 2), (yy + 0.5 - h / 2) / (h / 2)
    d = np.sqrt(dx * dx + dy * dy)
    grain = _noise(w, h, 3)
    out = np.zeros((h, w, 4), np.uint8)
    lip = (d <= 1) & (d > 0.8)
    lit = (dx > 0.2) & (dy < 0.3)
    stone = np.where(lit[..., None], STONE_HI, np.where((dy > 0.4)[..., None], STONE_LO, STONE))
    crack = (grain < 0.12) | (np.abs(np.arctan2(dy, dx) * 5 % 1 - 0.5) < 0.04)
    stone = np.where(crack[..., None], STONE_LO, stone)
    heat = (0.25 + 0.12 * stage) * (0.75 + 0.25 * glow / 7)
    depth = np.clip(1 - d / 0.72, 0, 1)
    ember = depth * heat * (0.6 + 0.4 * (dy > 0))
    level = np.clip((ember * 4).astype(int), 0, 2)
    sparks = (ember > 0.22) & (_noise(w, h, 11 + glow) < ember)
    hole = np.where((d > 0.45)[..., None], HOLE, HOLE_LO)
    hole = np.where(sparks[..., None], np.array(EMBER)[level], hole)
    hole = np.where(((d <= 0.8) & (d > 0.72))[..., None], HOLE_LO, hole)
    out[..., :3] = np.where(lip[..., None], stone, hole)
    out[..., 3] = np.where(d <= 1, 255, 0)
    return Image.fromarray(out, "RGBA")


def _shear(image: Image.Image, side: str) -> Image.Image:
    """Lean a flat sprite onto a back wall: the back row falls to the right, the back column to the left."""
    src = np.array(image)
    h, w = src.shape[:2]
    lift = w // 2 + 1
    out = np.zeros((h + lift, w, 4), np.uint8)
    for x in range(w):
        dy = x // 2 if side == "r" else (w - 1 - x) // 2
        out[dy:dy + h, x] = src[:, x]
    return Image.fromarray(out, "RGBA")


@lru_cache(maxsize=4)
def niche(side: str) -> Image.Image:
    """An empty arched recess cut into the wall, leaning with it: dark inside, a worn stone lip below."""
    b = Buf(NICHE_W, NICHE_H)
    b.rect(1, 2, NICHE_W - 2, NICHE_H - 3, RECESS)
    b.rect(2, 1, NICHE_W - 4, 1, RECESS)
    b.rect(1, NICHE_H - 4, NICHE_W - 2, 3, RECESS_LO)
    b.rect(2, 0, NICHE_W - 4, 1, SLAB_LO)
    b.px(1, 1, SLAB_LO)
    b.px(NICHE_W - 2, 1, SLAB_LO)
    b.rect(0, 2, 1, NICHE_H - 3, SLAB_LO)
    b.rect(NICHE_W - 1, 2, 1, NICHE_H - 3, SLAB_LO)
    b.rect(0, NICHE_H - 1, NICHE_W, 1, SLAB_HI)
    return _shear(to_image(b), side)


@lru_cache(maxsize=8)
def skull(hot: bool = False, tilt: int = 0) -> Image.Image:
    """A small skull, facing out: ivory dome, ink sockets, a nose notch and teeth; ``hot`` glows candle-gold."""
    hi, mid, lo = ((255, 236, 170), (246, 214, 140), (186, 140, 80)) if hot else (BONE_HI, BONE, BONE_LO)
    b = Buf(SKULL_W, SKULL_H)
    b.rect(1, 0, 5, 1, mid)
    b.rect(0, 1, 7, 3, mid)
    b.rect(1, 1, 2, 1, hi)
    b.rect(0, 3, 1, 1, lo)
    b.rect(1, 4, 5, 1, mid)
    b.rect(6, 1, 1, 3, lo)
    b.px(1 + (tilt > 0), 2, SOCKET)
    b.px(2 + (tilt > 0), 2, SOCKET)
    b.px(4 + (tilt > 0), 2, SOCKET)
    b.px(5, 2, SOCKET)
    b.px(3, 3, SOCKET)
    b.rect(1, 5, 5, 1, lo)
    for x in (1, 3, 5):
        b.px(x, 5, mid)
    b.rect(2, 6, 3, 1, lo)
    return to_image(b)


@lru_cache(maxsize=32)
def plaque(count: int, scale: int) -> Image.Image:
    """A carved stone slab reading ``"<n> forgotten"``, at ``scale`` with the words in the chosen face."""
    from cli_avatars.app import art_words as words

    font = words.face(9, True)
    text = f"{count} forgotten"
    w = words.cells(words.width(text, font) + 14 * scale, scale) + 2
    h = words.cells(words.line(font) + 6 * scale, scale) + 3
    b = Buf(w, h)
    b.rect(1, 0, w - 2, h - 2, SLAB)
    b.rect(0, 1, w, h - 4, SLAB)
    b.rect(1, 0, w - 2, 1, SLAB_HI)
    b.rect(0, 1, 1, h - 4, SLAB_HI)
    b.rect(1, h - 2, w - 2, 2, SLAB_LO)
    b.rect(w - 1, 1, 1, h - 3, SLAB_LO)
    b.rect(2, 2, w - 4, h - 6, (82, 74, 98))
    for x, y in ((3, 3), (w - 4, 3), (3, h - 5), (w - 4, h - 5)):
        b.px(x, y, SLAB_LO)
    image = words.up(to_image(b), scale)
    words.write(image, image.width // 2, 2 * scale, text, CARVE, font, shadow=SLAB_LO, align="c",
                box=(h - 6) * scale)
    return image


@lru_cache(maxsize=PUFF_FRAMES)
def puff(frame: int) -> Image.Image:
    """Stone dust thrown up by a sliding wall: a grey-tan cloud that billows and thins over ``PUFF_FRAMES``."""
    t = frame / max(1, PUFF_FRAMES - 1)
    r = 2.5 + 4.5 * t
    size = 16
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx + 0.5 - size / 2, (yy + 0.5 - size / 2) * 1.6) / r
    grain = _noise(size, size, frame)
    alpha = np.clip((1 - d) * 1.8, 0, 1) * 235 * (1 - 0.7 * t) * (grain < 0.92 - 0.3 * t)
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = DUST
    out[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(out, "RGBA")
