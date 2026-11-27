"""IDLE-PROPS.1 art drawn in code: the six idle objects, each with a small loop while in use, and the task table.

``frame(kind, used, step)`` is one of ``STEPS`` frames: the hearth always burns (higher and with sparks while hands
warm at it); dice tumble across the table; the well's bucket climbs and drips; the lectern's pages turn under a
candle; the black cat sleeps curled by its bowl, and eats with its tail swishing when fed; a glint runs along the
rack's blade while it is polished. ``table(doing, todo, blocked)`` is a project room's task table with its cards:
gold-sealed doing cards, parchment todo cards, an amber flag while one is blocked. Original designs, kit palette.
"""

from __future__ import annotations

import math
from functools import lru_cache

from cli_avatars.app.park_px import (
    AMBER,
    EMBER,
    FLAME,
    GLOW,
    IRON,
    IRON_D,
    IRON_L,
    STONE,
    STONE_D,
    STONE_H,
    STONE_L,
    WATER,
    WATER_L,
    WOOD,
    WOOD_D,
    WOOD_L,
    Pad,
    Sprite,
    mix,
)

STEPS = 8
PAPER, PAPER_D, SEAL, BLOCK = (226, 206, 160), (176, 152, 110), (196, 60, 50), (255, 179, 71)
FUR, FUR_L, EYE = (22, 18, 30), (58, 52, 74), (200, 220, 90)


@lru_cache(maxsize=None)
def frame(kind: str, used: bool, step: int) -> Sprite:
    return {"hearth": _hearth, "dice": _dice, "well": _well, "lectern": _lectern, "cat": _cat,
            "rack": _rack}[kind](used, step % STEPS)


def _hearth(used: bool, step: int) -> Sprite:
    """A ring of stones round a log fire; the flames lick higher while two warm their hands."""
    p = Pad(40, 44, 20, 32)
    p.shadow(15, 5)
    for i in range(10):
        ang = i / 10 * math.tau
        x, y = 20 + 13 * math.cos(ang), 30 + 6 * math.sin(ang)
        p.ellipse(x, y, 3.2, 2.2, STONE_L if i % 3 else STONE)
        p.dot(x - 1, y - 1, STONE_H)
    p.line([(13, 31), (27, 28)], WOOD_D, 3)
    p.line([(13, 28), (27, 31)], WOOD, 3)
    p.ellipse(20, 30, 6, 2.5, EMBER)
    tall = 14 if used else 9
    for i, (dx, phase) in enumerate(((-4, 0.0), (0, 0.33), (4, 0.66), (-2, 0.5), (2, 0.15))):
        h = tall * (0.65 + 0.35 * math.sin(math.tau * (step / STEPS + phase))) * (1.0 if i < 3 else 0.6)
        x = 20 + dx
        for k in range(int(h)):
            t = k / max(1.0, h)
            colour = mix(mix(EMBER, AMBER, min(1.0, t * 2)), FLAME, max(0.0, t * 2 - 1.0))
            width = max(0.5, 2.6 * (1.0 - t))
            p.line([(x - width + math.sin(t * 4 + step) * 0.6, 29 - k), (x + width, 29 - k)], colour)
    if used:
        for i in range(3):
            k = (step / STEPS + i / 3) % 1.0
            p.dot(20 + 6 * math.sin(math.tau * (k + i * 0.3)), 26 - tall - 10 * k, GLOW)
    return p.done(outline=False)


def _dice(used: bool, step: int) -> Sprite:
    """A round table for two with a leather cup and two bone dice that tumble while a game is on."""
    p = Pad(44, 34, 22, 26)
    p.shadow(15, 5)
    for sx in (-15, 15):
        p.box(sx / 16 * 0.5 - 0.15, -0.15, sx / 16 * 0.5 + 0.15, 0.15, 0, 6, WOOD_L, WOOD, WOOD_D)
    p.line([(22, 26), (22, 16)], WOOD_D, 3)
    p.ellipse(22, 15, 13, 6, WOOD_D)
    p.ellipse(22, 14, 12, 5, WOOD)
    p.ellipse(20, 13, 8, 3, WOOD_L)
    p.rect(14, 8, 17, 13, (96, 52, 34))
    p.rect(14, 8, 15, 13, (128, 74, 46))
    spots = ((26, 13), (29, 14)) if not used else (
        ((22 + 6 * math.cos(step), 13 - abs(math.sin(step * 0.8)) * 4), (28 - 3 * math.sin(step * 1.3), 14)))
    for i, (x, y) in enumerate(spots):
        p.rect(round(x) - 1, round(y) - 1, round(x) + 1, round(y) + 1, PAPER)
        p.dot(x, y, (40, 30, 30) if (step + i) % 2 or not used else SEAL)
    return p.done()


def _well(used: bool, step: int) -> Sprite:
    """A round stone well under a small wooden roof; a bucket rises on its rope and drips while in use."""
    p = Pad(40, 54, 20, 44)
    p.shadow(15, 5)
    p.ellipse(20, 38, 13, 6, STONE_D)
    p.rect(7, 30, 33, 38, STONE)
    for x in range(8, 33, 5):
        p.line([(x, 31), (x, 37)], STONE_D)
    p.ellipse(20, 30, 13, 6, STONE_L)
    p.ellipse(20, 30, 9, 4, (14, 16, 30))
    p.ellipse(20, 31, 6, 2, WATER if not used else mix(WATER, WATER_L, 0.3))
    for x in (9, 31):
        p.line([(x, 30), (x, 8)], WOOD, 2)
    p.poly([(5, 10), (20, 2), (35, 10), (20, 14)], WOOD_D)
    p.poly([(5, 10), (20, 2), (20, 6), (8, 11)], WOOD_L)
    p.line([(9, 14), (31, 14)], WOOD_L)
    depth = 22 - (8 * (0.5 + 0.5 * math.sin(math.tau * step / STEPS)) if used else 0)
    p.line([(20, 14), (20, depth)], STRAW_ROPE)
    p.rect(17, round(depth), 23, round(depth) + 4, WOOD)
    p.rect(17, round(depth), 18, round(depth) + 4, WOOD_L)
    if used:
        p.dot(20, depth + 6 + step % 3 * 2, WATER_L)
    return p.done()


STRAW_ROPE = (180, 150, 96)


def _lectern(used: bool, step: int) -> Sprite:
    """A slanted wooden lectern with a thick open book and a candle; pages turn while someone reads."""
    p = Pad(32, 46, 16, 40)
    p.shadow(9, 3)
    p.rect(14, 18, 18, 40, WOOD)
    p.rect(14, 18, 15, 40, WOOD_L)
    p.rect(10, 38, 22, 40, WOOD_D)
    p.poly([(5, 18), (27, 12), (29, 17), (7, 23)], WOOD_D)
    p.poly([(7, 16), (16, 13), (17, 18), (8, 21)], PAPER)
    p.poly([(16, 13), (26, 10), (27, 15), (17, 18)], PAPER_D)
    for y in (16, 18):
        p.line([(9, y), (14, y - 1)], (120, 100, 80))
    if used:
        k = (step % 4) / 3.0
        tip = (17 + 9 * math.cos(math.pi * k), 9 + 4 * math.sin(math.pi * k))
        p.poly([(16, 13), tip, (17, 18)], PAPER)
    p.rect(26, 6, 27, 11, (230, 220, 200))
    flick = 1 + (step % 3 == 0)
    p.line([(26, 5), (26, 5 - flick)], GLOW)
    p.dot(26, 4 - flick, FLAME)
    return p.done()


def _cat(used: bool, step: int) -> Sprite:
    """A black cat by its bowl: curled asleep, breathing slow; fed, it eats with its tail swishing."""
    p = Pad(36, 28, 18, 22)
    p.shadow(12, 3)
    p.ellipse(27, 20, 5, 2.2, (120, 120, 140))
    p.ellipse(27, 19, 3.5, 1.2, (210, 190, 150))
    if not used:
        breath = 0.6 * math.sin(math.tau * step / STEPS)
        p.ellipse(13, 17, 8, 4.5 + breath, FUR)
        p.ellipse(12, 15, 5, 2.5, FUR_L)
        p.ellipse(7, 17, 3.5, 3, FUR)
        p.poly([(5, 15), (6, 11), (8, 14)], FUR)
        p.poly([(8, 14), (10, 11), (10, 15)], FUR)
        p.line([(19, 20), (12, 21), (6, 20)], FUR, 2)
        p.line([(6, 17), (8, 17)], FUR_L)
    else:
        p.ellipse(16, 15, 7, 4, FUR)
        p.ellipse(15, 13, 5, 2, FUR_L)
        bob = step % 2
        p.ellipse(23, 15 + bob, 3.5, 3, FUR)
        p.poly([(21, 12 + bob), (21, 9 + bob), (23, 12 + bob)], FUR)
        p.poly([(24, 12 + bob), (26, 9 + bob), (26, 13 + bob)], FUR)
        p.dot(24, 15 + bob, EYE)
        for x in (12, 19):
            p.line([(x, 18), (x, 21)], FUR, 2)
        swing = 4 * math.sin(math.tau * step / STEPS)
        p.line([(9, 15), (5, 11 + swing), (4, 6 + swing)], FUR, 2)
    return p.done()


def _rack(used: bool, step: int) -> Sprite:
    """A wooden weapon rack: a sword, an axe and a spear; a glint runs down the sword while it is polished."""
    p = Pad(40, 50, 20, 42)
    p.shadow(14, 4)
    for x in (7, 33):
        p.line([(x, 42), (x, 10)], WOOD, 3)
    p.line([(6, 14), (34, 14)], WOOD_L, 2)
    p.line([(6, 36), (34, 36)], WOOD_D, 2)
    p.line([(13, 38), (13, 6)], IRON_L, 2)
    p.line([(10, 32), (16, 32)], AMBER, 2)
    p.line([(13, 33), (13, 38)], WOOD_D, 2)
    p.line([(21, 40), (21, 10)], WOOD_D, 2)
    p.poly([(21, 10), (26, 7), (27, 15), (21, 16)], IRON)
    p.line([(26, 8), (27, 14)], IRON_L)
    p.line([(29, 41), (29, 4)], WOOD, 2)
    p.poly([(29, 0), (31, 5), (29, 8), (27, 5)], IRON_L)
    if used:
        y = 6 + (step / STEPS) * 26
        for k, colour in ((0, FLAME), (1, GLOW), (-1, GLOW)):
            p.dot(13, y + k, colour)
        p.dot(11, y - 2, FLAME)
        p.dot(15, y + 2, FLAME)
    return p.done()


@lru_cache(maxsize=64)
def table(doing: int, todo: int, blocked: int) -> Sprite:
    """The room's task table: a long board on trestles, its cards laid out, a candle, a flag while one is blocked."""
    p = Pad(56, 40, 28, 30)
    p.shadow(20, 5)
    for u in (-0.7, 0.7):
        p.box(u - 0.12, -0.3, u + 0.12, 0.3, 0, 9, WOOD_L, WOOD, WOOD_D)
    p.box(-0.95, -0.45, 0.95, 0.45, 9, 12, WOOD_L, WOOD, WOOD_D)
    for i in range(min(3, doing)):
        x, y = p.iso(-0.6 + i * 0.36, -0.1, 12)
        p.rect(round(x) - 3, round(y) - 2, round(x) + 3, round(y) + 2, PAPER)
        p.dot(x, y, SEAL)
        p.dot(x + 1, y, SEAL)
        p.line([(x - 2, y - 2), (x + 2, y - 2)], GLOW)
    for i in range(min(3, todo)):
        x, y = p.iso(-0.2 + i * 0.32, 0.22, 12)
        p.rect(round(x) - 3, round(y) - 2, round(x) + 3, round(y) + 2, PAPER_D)
        p.line([(x - 2, y), (x + 2, y)], (120, 100, 80))
    x, y = p.iso(0.75, -0.3, 12)
    p.rect(round(x), round(y) - 6, round(x) + 1, round(y), (230, 220, 200))
    p.dot(x, y - 7, GLOW)
    p.dot(x, y - 8, FLAME)
    if blocked:
        x, y = p.iso(-0.85, -0.35, 12)
        p.line([(x, y), (x, y - 14)], IRON_D)
        p.poly([(x + 1, y - 14), (x + 8, y - 11), (x + 1, y - 8)], BLOCK)
    return p.done()


def kinds() -> tuple[str, ...]:
    return ("hearth", "dice", "well", "lectern", "cat", "rack")


__all__ = ["frame", "table", "kinds", "IRON"]
