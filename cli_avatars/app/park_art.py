"""PARK.1 art drawn in code: the night lawn, three dark sculptures, benches, training things and lanterns. No Tk.

``stamp`` paints the still park into the composed rooms image (desktop and phone): moonlit grass with tufts,
flowers and glowing mushrooms, a stepping-stone path from the gate, warm pools under the lanterns, then each piece
in depth order. ``fx`` is one animated layer the desktop lays over it: lantern halos that breathe, fireflies on
slow loops, the obelisk's runes pulsing. All designs are original; pixels are on the kit's 16x8 grid at 1x.
"""

from __future__ import annotations

import math
import zlib
from functools import lru_cache

from PIL import Image

from cli_avatars.app import park
from cli_avatars.app.park_px import (
    AMBER,
    FLAME,
    GLOW,
    HALF_H,
    HALF_W,
    IRON,
    IRON_D,
    IRON_L,
    MOSS,
    MOSS_L,
    RUNE,
    STONE,
    STONE_D,
    STONE_H,
    STONE_L,
    STRAW,
    STRAW_D,
    STRAW_L,
    WOOD,
    WOOD_D,
    WOOD_L,
    Pad,
    Sprite,
    mix,
    paste,
)

GRASS_D, GRASS, GRASS_L, TUFT = (22, 40, 36), (27, 48, 41), (32, 57, 46), (52, 90, 60)
FLOWERS = ((132, 150, 214), (176, 140, 210), (220, 210, 170))
SHROOM = (96, 214, 196)
FX_STEPS = 24
FIREFLIES = 14


def _hash(*parts) -> int:
    return zlib.crc32(repr(parts).encode())


def _px(u: float, v: float) -> tuple[float, float]:
    return (u - v) * HALF_W, (u + v) * HALF_H


def stamp(image, layout: dict | None) -> bool:
    """Paint the park into ``image`` (the composed rooms at 1x); False when the layout has none."""
    room = park.lawn(layout)
    if room is None:
        return False
    left, top = image.info.get("origin", (0, 0))
    _lawn(image, room, left, top)
    for piece in sorted(park.pieces(layout), key=lambda p: (p.cell[0] + p.cell[1], p.cell[0])):
        x, y = _px(piece.cell[0] + 0.5, piece.cell[1] + 0.5)
        sprite = SPRITES[piece.piece](piece.flip)
        paste(image, sprite, x - left, y - top)
    return True


def _lawn(image, room: dict, left: int, top: int) -> None:
    (u0, v0), (w, h) = room["origin"], room["size"]
    a, b = u0 + 1, v0 + 1
    c, d = u0 + w, v0 + h
    xs = [_px(u, v)[0] for u, v in ((a, b), (c, b), (c, d), (a, d))]
    ys = [_px(u, v)[1] for u, v in ((a, b), (c, b), (c, d), (a, d))]
    lamps = [(p.cell[0] + 0.5, p.cell[1] + 0.5) for p in park.pieces({"rooms": [room]}) if p.piece == "lantern"]
    stones = _path(room)
    px = image.load()
    for y in range(int(min(ys)), int(max(ys)) + 3):
        for x in range(int(min(xs)), int(max(xs)) + 1):
            u, v = (x / HALF_W + y / HALF_H) / 2.0, (y / HALF_H - x / HALF_W) / 2.0
            ix, iy = x - left, y - top
            if not (0 <= ix < image.width and 0 <= iy < image.height):
                continue
            if not (a <= u < c and b <= v < d):
                continue
            px[ix, iy] = (*_grass(x, y, u - a, v - b, lamps, u, v, stones), 255)


def _grass(x: int, y: int, du: float, dv: float, lamps, u: float, v: float, stones) -> tuple:
    n = _hash(x, y) % 1000 / 1000.0
    blob = _hash(int(u * 3), int(v * 3)) % 100 / 100.0
    colour = GRASS_D if blob < 0.3 else GRASS_L if blob > 0.75 else GRASS
    if n < 0.12:
        colour = mix(colour, GRASS_D, 0.6)
    if _hash(x, y // 3, "t") % 41 == 0 or _hash(x, (y - 1) // 3, "t") % 41 == 0:
        colour = TUFT
    if n > 0.9985:
        colour = FLOWERS[_hash(x, y, "f") % 3]
    elif n < 0.0008:
        colour = SHROOM
    for su, sv, r in stones:
        k = ((u - su) / r) ** 2 + ((v - sv) / (r * 0.75)) ** 2
        if k < 1.0:
            colour = mix(STONE_L if k < 0.45 else STONE, STONE_D, 0.25 if n < 0.3 else 0.0)
    edge = min(du, dv, 1.0)
    colour = mix(colour, (6, 6, 14), 0.45 * (1.0 - edge))
    glow = sum(max(0.0, 1.0 - math.dist((u, v), lamp) / 2.4) ** 2 for lamp in lamps)
    colour = mix(colour, mix(colour, GLOW, 0.55), min(1.0, glow))
    return mix(colour, (70, 90, 150), 0.08)


def _path(room: dict) -> list[tuple[float, float, float]]:
    """Stepping stones from the gate (the west wall's first tiles) to the middle of the lawn."""
    (u0, v0) = room["origin"]
    out = []
    for i in range(7):
        t = i / 6.0
        u = u0 + 1.4 + t * 4.6 + (_hash("pu", i) % 7 - 3) * 0.04
        v = v0 + 1.6 + t * 2.4 + (_hash("pv", i) % 7 - 3) * 0.04
        out.append((u, v, 0.26 + (_hash("pr", i) % 3) * 0.03))
    return out


# --- pieces ------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def statue(_flip: bool = False) -> Sprite:
    """A hooded figure on a plinth, hands folded, two faint teal eyes in the hood's dark."""
    p = Pad(26, 46, 13, 40)
    p.shadow(11, 4)
    p.box(-0.42, -0.42, 0.42, 0.42, 0, 6, STONE_L, STONE, STONE_D)
    for y in range(9, 34):
        k = (y - 9) / 25.0
        half = 3 + 4.5 * k
        for x in range(round(13 - half), round(13 + half) + 1):
            side = (x - 13) / max(1.0, half)
            p.dot(x, y, mix(STONE_H, STONE_D, 0.5 + 0.5 * side) if side < 0.6 else STONE_D)
    p.ellipse(13, 10, 4.5, 5, STONE_L)
    p.ellipse(14, 10, 3.5, 4, STONE)
    p.ellipse(13, 12, 2.5, 3, (10, 8, 18))
    p.dot(12, 12, (70, 160, 150))
    p.dot(14, 12, (70, 160, 150))
    p.ellipse(13, 22, 2.5, 1.6, STONE_H)
    for x, y in ((9, 32), (10, 33), (16, 31), (17, 33), (8, 34)):
        p.dot(x, y, MOSS_L if (x + y) % 2 else MOSS)
    return p.done()


@lru_cache(maxsize=None)
def obelisk(_flip: bool = False) -> Sprite:
    """A tall broken obelisk, its top snapped off at a slant, three runes cut down its face."""
    p = Pad(26, 54, 11, 48)
    p.shadow(10, 4)
    p.box(-0.4, -0.4, 0.4, 0.4, 0, 5, STONE_L, STONE, STONE_D)
    p.poly([(7, 43), (11, 45), (11, 12), (8, 14)], STONE_L)
    p.poly([(11, 45), (15, 43), (14, 8), (11, 12)], STONE_D)
    p.poly([(8, 14), (11, 12), (14, 8), (10, 10)], STONE_H)
    for y, shape in ((20, ((0, 0), (1, 1), (0, 2), (-1, 1))), (28, ((0, 0), (0, 1), (0, 2), (1, 1))),
                     (36, ((-1, 0), (0, 1), (1, 0), (0, 2)))):
        for dx, dy in shape:
            p.dot(9 + dx, y + dy, mix(RUNE, STONE, 0.45))
    p.box(0.55, 0.1, 0.95, 0.4, 0, 4, STONE_L, STONE, STONE_D)
    p.dot(8, 42, MOSS_L)
    p.dot(9, 43, MOSS)
    return p.done()


@lru_cache(maxsize=None)
def gargoyle(_flip: bool = False) -> Sprite:
    """A crouched winged gargoyle on a block: horns, folded wings, ember eyes."""
    p = Pad(34, 40, 17, 34)
    p.shadow(12, 4)
    p.box(-0.42, -0.42, 0.42, 0.42, 0, 8, STONE_L, STONE, STONE_D)
    p.poly([(9, 22), (3, 8), (6, 9), (8, 5), (11, 12)], STONE_D)
    p.poly([(25, 22), (31, 8), (28, 9), (26, 5), (23, 12)], STONE_D)
    p.ellipse(17, 19, 6, 6, STONE)
    p.ellipse(16, 18, 4, 4, STONE_L)
    p.ellipse(17, 11, 4, 3.5, STONE_L)
    p.line([(14, 9), (12, 5)], STONE_H)
    p.line([(20, 9), (22, 5)], STONE_H)
    p.dot(15, 11, (190, 70, 40))
    p.dot(19, 11, (190, 70, 40))
    p.rect(13, 24, 15, 26, STONE)
    p.rect(19, 24, 21, 26, STONE)
    p.dot(11, 27, MOSS_L)
    return p.done()


@lru_cache(maxsize=None)
def bench(_flip: bool = False) -> Sprite:
    """A stone bench two tiles long, worn smooth on top."""
    p = Pad(50, 30, 17, 14)
    p.ellipse(p.iso(1.0, 0.0)[0], p.iso(1.0, 0.0)[1] + 1, 22, 5, (7, 4, 11, 115))
    for u in (0.1, 1.55):
        p.box(u - 0.4, -0.2, u - 0.1, 0.2, 0, 5, STONE_L, STONE, STONE_D)
    p.box(-0.45, -0.32, 1.95, 0.32, 5, 8, STONE_H, STONE_L, STONE)
    p.line([p.iso(-0.3, -0.2, 8), p.iso(1.8, -0.2, 8)], mix(STONE_H, (255, 255, 255), 0.25))
    return p.done()


@lru_cache(maxsize=None)
def dummy(flip: bool = False) -> Sprite:
    """A straw training dummy on a post: sack head with a stitched cross, rope bands, one arm out."""
    p = Pad(26, 42, 13, 38)
    p.shadow(8, 3)
    p.line([(9, 38), (17, 38)], WOOD_D, 2)
    p.line([(13, 36), (13, 10)], WOOD, 3)
    p.rect(9, 15, 17, 28, STRAW)
    p.rect(9, 15, 10, 28, STRAW_L)
    p.rect(16, 15, 17, 28, STRAW_D)
    for y in (18, 25):
        p.line([(9, y), (17, y)], WOOD_D)
    p.line([(3, 19), (23, 17) if not flip else (23, 21)], WOOD, 2)
    p.ellipse(13, 9, 4.5, 4.5, STRAW)
    p.ellipse(12, 8, 2.5, 2.5, STRAW_L)
    p.line([(11, 7), (15, 11)], WOOD_D)
    p.line([(15, 7), (11, 11)], WOOD_D)
    return p.done()


@lru_cache(maxsize=None)
def rack(_flip: bool = False) -> Sprite:
    """An iron weight rack: two uprights, a bar with round plates, two hand weights on the shelf below."""
    p = Pad(40, 34, 20, 28)
    p.shadow(15, 4)
    for u in (-0.38, 0.38):
        x, y = p.iso(u, 0)
        p.line([(x, y), (x, y - 18)], IRON_D, 2)
    a, b = p.iso(-0.5, 0, 17), p.iso(0.5, 0, 17)
    p.line([a, b], IRON_L, 2)
    for k in (0.06, 0.94):
        x, y = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        p.ellipse(x, y, 3, 5, IRON)
        p.ellipse(x - 1, y - 1, 1.5, 2.5, IRON_L)
    c, d = p.iso(-0.38, 0, 6), p.iso(0.38, 0, 6)
    p.line([c, d], WOOD, 2)
    for k in (0.3, 0.7):
        x, y = c[0] + (d[0] - c[0]) * k, c[1] + (d[1] - c[1]) * k - 2
        p.line([(x - 3, y), (x + 3, y)], IRON_L)
        p.rect(round(x) - 4, round(y) - 1, round(x) - 3, round(y) + 1, IRON)
        p.rect(round(x) + 3, round(y) - 1, round(x) + 4, round(y) + 1, IRON)
    return p.done()


@lru_cache(maxsize=None)
def post(_flip: bool = False) -> Sprite:
    """A sparring post: a scarred log set in a ring of stones, three pegs for arms and one for a leg."""
    p = Pad(28, 42, 14, 37)
    p.shadow(9, 3)
    for i in range(7):
        ang = i / 7 * math.tau
        p.ellipse(14 + 7 * math.cos(ang), 37 + 3 * math.sin(ang), 2, 1.3, STONE_L if i % 2 else STONE)
    p.rect(11, 6, 16, 36, WOOD)
    p.rect(11, 6, 12, 36, WOOD_L)
    p.rect(15, 6, 16, 36, WOOD_D)
    p.ellipse(13.5, 6, 2.6, 1.2, WOOD_L)
    for y, d in ((12, -1), (15, 1), (19, -1), (29, 1)):
        x = 11 if d < 0 else 16
        p.line([(x, y), (x + 5 * d, y + 1)], WOOD_L, 2)
    for y in (22, 26):
        p.dot(13, y, WOOD_D)
        p.dot(14, y + 1, WOOD_D)
    return p.done()


@lru_cache(maxsize=None)
def lantern(_flip: bool = False) -> Sprite:
    """An iron lamp post with a warm glass lantern and a little cap."""
    p = Pad(16, 40, 8, 37)
    p.shadow(4, 1.5)
    p.rect(7, 12, 8, 37, IRON_D)
    p.rect(6, 35, 9, 37, IRON)
    p.rect(4, 5, 11, 12, IRON)
    p.rect(5, 6, 10, 11, AMBER)
    p.rect(6, 7, 9, 10, GLOW)
    p.dot(7, 8, FLAME)
    p.poly([(3, 5), (8, 1), (12, 5)], IRON_L)
    return p.done()


SPRITES = {"statue": statue, "obelisk": obelisk, "gargoyle": gargoyle, "bench": bench, "dummy": dummy,
           "rack": rack, "post": post, "lantern": lantern}


# --- the animated layer --------------------------------------------------------------------------------------------
def fx_box(layout: dict | None) -> tuple[float, float, int, int] | None:
    """Global pixel ``(x, y)`` of the layer's top left and its size, or None without a park."""
    room = park.lawn(layout)
    if room is None:
        return None
    (u0, v0), (w, h) = room["origin"], room["size"]
    x0, _ = _px(u0, v0 + h)
    x1, _ = _px(u0 + w, v0)
    _, y0 = _px(u0, v0)
    _, y1 = _px(u0 + w, v0 + h)
    return x0, y0 - 40, int(x1 - x0) + 1, int(y1 - y0) + 41


@lru_cache(maxsize=4 * FX_STEPS)
def fx(layout_key: str, step: int, box: tuple, lamps: tuple, runes: tuple, flies: tuple) -> Image.Image:
    """Halos, fireflies and rune glow for ``step`` of ``FX_STEPS``; ``layout_key`` keys the cache."""
    x0, y0, w, h = box
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = image.load()
    t = step / FX_STEPS
    for lx, ly in lamps:
        k = 0.75
        cx, cy = lx - x0, ly - y0 - 31
        for y in range(max(0, int(cy - 11)), min(h, int(cy + 12))):
            for x in range(max(0, int(cx - 16)), min(w, int(cx + 17))):
                d = ((x - cx) / 16) ** 2 + ((y - cy) / 11) ** 2
                if d < 1.0 and (x + y) % 2 == 0 or d < 0.35:
                    a = int(70 * k * (1.0 - d) ** 2)
                    if a > 6:
                        px[x, y] = (*GLOW, a)
    for (rx, ry) in runes:
        a = 110
        for dx, dy in ((0, 0), (1, 1), (0, 2), (-1, 1)):
            x, y = int(rx - x0 + dx), int(ry - y0 + dy)
            if 0 <= x < w and 0 <= y < h:
                px[x, y] = (*RUNE, max(0, a))
    for i, (fx_, fy, phase, size) in enumerate(flies):
        ang = math.tau * (t + phase)
        x = int(fx_ - x0 + 9 * math.sin(ang + i))
        y = int(fy - y0 - 14 + 5 * math.sin(2 * ang + i * 0.5))
        if 1 <= x < w - 1 and 1 <= y < h - 1:
            px[x, y] = (230, 255, 170, 255)
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))[:size + 2]:
                px[nx, ny] = (190, 240, 120, 120)
    return image


def fx_inputs(layout: dict | None) -> tuple | None:
    """``(box, lamps, runes, flies)`` in global pixels for ``fx``; None without a park."""
    box = fx_box(layout)
    if box is None:
        return None
    pieces = park.pieces(layout)
    lamps = tuple(_px(p.cell[0] + 0.5, p.cell[1] + 0.5) for p in pieces if p.piece == "lantern")
    runes = []
    for p in pieces:
        if p.piece == "obelisk":
            x, y = _px(p.cell[0] + 0.5, p.cell[1] + 0.5)
            runes += [(x - 2, y - 28), (x - 2, y - 20), (x - 2, y - 12)]
    room = park.lawn(layout)
    (u0, v0), (w, h) = room["origin"], room["size"]
    flies = []
    for i in range(FIREFLIES):
        u = u0 + 1.5 + (_hash("fu", i) % 100) / 100.0 * (w - 2.5)
        v = v0 + 1.5 + (_hash("fv", i) % 100) / 100.0 * (h - 2.5)
        x, y = _px(u, v)
        flies.append((x, y, (_hash("fp", i) % 100) / 100.0, i % 2))
    return box, lamps, tuple(runes), tuple(flies)
