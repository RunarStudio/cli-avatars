"""MESSENGER art drawn in code at 1x (no Tk): the courier, the wax seal flash, the lit card, the ribbon and the note.

The courier is a small hooded runner in a teal cloak with a feathered cap, a satchel strap across the chest and a
sealed parchment scroll held under the near arm; six walk frames bob and swing the cloak. On arrival a wax seal is
pressed (the disc pops, a gold ring spreads, sparks fly). The affected room's card glows under a crimson ribbon.
"""

from __future__ import annotations

import math
from functools import lru_cache

from cli_avatars.app.throne_px import Buf, t35, to_image

W, H = 22, 30
STEPS = 6
FLASH_STEPS = 8
CLOAK, CLOAK_HI, CLOAK_LO = (46, 104, 112), (78, 150, 150), (24, 58, 70)
TRIM, TRIM_LO = (226, 178, 74), (150, 104, 40)
SKIN, SKIN_LO = (232, 184, 140), (170, 118, 88)
CAP, FEATHER, FEATHER_LO = (36, 46, 74), (214, 64, 58), (130, 30, 40)
STRAP, BAG, BAG_LO = (110, 70, 40), (140, 92, 52), (86, 54, 30)
BOOT, LEG = (44, 32, 30), (60, 66, 92)
PAPER, PAPER_LO, PAPER_HI = (236, 222, 184), (184, 160, 116), (252, 244, 220)
WAX, WAX_HI, WAX_LO = (196, 40, 46), (240, 96, 90), (110, 16, 26)
RIBBON, RIBBON_LO, RIBBON_HI = (164, 30, 48), (96, 14, 30), (210, 70, 80)
GLOW = (255, 206, 110)
INK = (250, 238, 206)
BOB = (0, -1, -1, 0, -1, -1)
STRIDE = (3, 1, -1, -3, -1, 1)


@lru_cache(maxsize=32)
def courier(step: int, walking: bool, face: int = 1):
    """One frame (``W`` x ``H``), feet on the bottom row, facing right; ``face`` -1 mirrors it."""
    from PIL import Image

    b = Buf(W, H)
    i = step % STEPS
    bob = BOB[i] if walking else (0 if (step // 3) % 2 == 0 else -1) * 0
    swing = STRIDE[i] if walking else 0
    _shadow(b, 11, H - 1)
    _legs(b, swing, bob)
    _bag(b, bob, swing)
    _cloak(b, bob, swing, walking, i)
    _head(b, bob)
    _scroll(b, bob, i if walking else 0)
    image = to_image(b)
    return image.transpose(Image.FLIP_LEFT_RIGHT) if face < 0 else image


def _shadow(b: Buf, cx: int, y: int) -> None:
    for dx in range(-7, 8):
        b.px(cx + dx, y, (0, 0, 0), 0.32 * (1 - abs(dx) / 8))
        if abs(dx) < 5:
            b.px(cx + dx, y - 1, (0, 0, 0), 0.14)


def _legs(b: Buf, swing: int, bob: int) -> None:
    top = 21 + bob
    for x0, dx, shade in ((9, -swing, 0.7), (12, swing, 1.0)):
        x = x0 + dx // 2
        b.rect(x, top, 2, H - 3 - top, LEG, shade)
        b.rect(x + dx // 3, H - 3, 3, 2, BOOT)
        b.px(x + dx // 3 + 2, H - 3, (90, 70, 60))


def _bag(b: Buf, bob: int, swing: int) -> None:
    y = 15 + bob
    b.rect(4, y, 5, 5, BAG)
    b.rect(4, y, 5, 1, BAG_LO)
    b.rect(4, y + 4, 5, 1, BAG_LO)
    b.px(6, y + 2, TRIM)


def _cloak(b: Buf, bob: int, swing: int, walking: bool, i: int) -> None:
    top, hem = 10 + bob, 23 + bob
    sway = (1 if i in (1, 2) else -1 if i in (4, 5) else 0) if walking else 0
    for y in range(top, hem + 1):
        k = (y - top) / max(1, hem - top)
        left = round(8 - 3 * k) + (sway if y > hem - 3 else 0)
        right = round(14 + 2 * k)
        b.rect(left, y, right - left, 1, CLOAK)
        b.px(left, y, CLOAK_LO)
        b.px(left + 1, y, CLOAK_LO, 0.5)
        b.px(right - 1, y, CLOAK_HI, 0.8)
    b.rect(round(5) + sway, hem, 11, 1, TRIM)
    b.rect(round(5) + sway, hem + 1, 11, 1, TRIM_LO, 0.8)
    for y in range(top + 1, hem - 1):
        x = 8 + (y - top) // 2
        if x < 15:
            b.px(x, y, STRAP)
    b.px(11, top + 5, TRIM)


def _head(b: Buf, bob: int) -> None:
    y = 3 + bob
    for row, (x0, x1) in enumerate(((10, 15), (9, 16), (8, 16), (8, 16), (8, 16), (9, 15), (10, 14))):
        b.rect(x0, y + row, x1 - x0, 1, CLOAK_LO if row < 2 else CLOAK)
    b.rect(12, y + 2, 4, 4, SKIN)
    b.rect(12, y + 2, 1, 4, SKIN_LO)
    b.px(14, y + 3, (34, 24, 30))
    b.rect(12, y + 5, 3, 1, SKIN_LO, 0.6)
    b.rect(9, y - 1, 7, 2, CAP)
    b.rect(8, y + 1, 9, 1, CAP)
    b.px(16, y + 1, TRIM)
    for k, (dx, dy) in enumerate(((-1, -1), (-2, -2), (-3, -2), (-4, -3), (-5, -3))):
        b.px(9 + dx, y + dy + 1, FEATHER if k < 4 else FEATHER_LO)
        b.px(9 + dx, y + dy + 2, FEATHER_LO, 0.7)


def _scroll(b: Buf, bob: int, i: int) -> None:
    """The parchment roll under the near arm, its wax seal toward the viewer; the arm hugs it."""
    y = 14 + bob + (1 if i in (2, 5) else 0)
    x0, x1 = 9, 20
    b.rect(x0, y, x1 - x0, 4, PAPER)
    b.rect(x0, y, x1 - x0, 1, PAPER_HI)
    b.rect(x0, y + 3, x1 - x0, 1, PAPER_LO)
    for x in (x0, x1 - 1):
        b.rect(x, y, 1, 4, PAPER_LO)
    b.px(x1 - 1, y + 1, (120, 96, 60))
    b.rect(14, y + 1, 3, 3, WAX)
    b.px(14, y + 1, WAX_HI)
    b.px(16, y + 3, WAX_LO)
    b.px(15, y + 4, WAX_LO)
    b.px(16, y + 5, RIBBON)
    b.rect(11, y - 1, 3, 6, CLOAK_HI)
    b.rect(11, y + 4, 3, 1, CLOAK)
    b.rect(12, y + 5, 2, 1, SKIN)


@lru_cache(maxsize=16)
def flash(step: int):
    """The wax seal pressed on arrival: the disc pops, a gold ring spreads and fades, eight sparks fly out."""
    side = 36
    b = Buf(side, side)
    t = min(step, FLASH_STEPS - 1) / (FLASH_STEPS - 1)
    c = side / 2
    ring = 5 + 12 * t
    for a in range(48):
        ang = a / 48 * math.tau
        b.px(round(c + math.cos(ang) * ring), round(c + math.sin(ang) * ring * 0.8), GLOW, 0.9 * (1 - t))
    for a in range(8):
        ang = a / 8 * math.tau + 0.2
        for r in range(3):
            d = 6 + 13 * t + r * 2
            b.px(round(c + math.cos(ang) * d), round(c + math.sin(ang) * d * 0.8), (255, 240, 190),
                 (1 - t) * (1 - r / 3))
    pop = 1.0 + 0.5 * math.sin(min(1.0, t * 2.5) * math.pi)
    r = 4.2 * pop
    for y in range(int(c - r) - 1, int(c + r) + 2):
        for x in range(int(c - r) - 1, int(c + r) + 2):
            d = math.hypot(x + 0.5 - c, y + 0.5 - c) / r
            if d <= 1.0:
                b.px(x, y, WAX_HI if d < 0.35 and x < c else WAX if d < 0.8 else WAX_LO)
    b.px(int(c), int(c), TRIM)
    b.px(int(c) - 1, int(c), TRIM, 0.6)
    return to_image(b)


@lru_cache(maxsize=16)
def halo(level: int, scale: int = 1):
    """A warm pulse under the lit card; ``level`` 0..7 is how bright."""
    from PIL import Image

    w, h = 40 * scale, 22 * scale
    b = Buf(w, h)
    k = 0.35 + 0.65 * level / 7
    for y in range(h):
        for x in range(w):
            d = math.hypot((x + 0.5 - w / 2) / (w / 2), (y + 0.5 - h / 2) / (h / 2))
            if d < 1.0:
                b.px(x, y, GLOW, (1 - d) ** 1.6 * 0.75 * k)
    return to_image(b) if scale == 1 else to_image(b).resize((w, h), Image.NEAREST)


@lru_cache(maxsize=16)
def card(level: int):
    """The affected room's task card: parchment with lines and a wax seal, edged in gold as it pulses."""
    b = Buf(18, 22)
    edge = tuple(int(a + (g - a) * level / 7) for a, g in zip(PAPER_LO, GLOW, strict=True))
    b.rect(1, 1, 16, 20, PAPER)
    b.rect(1, 1, 16, 1, PAPER_HI)
    for x, y, w, h in ((0, 1, 1, 20), (17, 1, 1, 20), (1, 0, 16, 1), (1, 21, 16, 1)):
        b.rect(x, y, w, h, edge)
    for y in (5, 8, 11):
        b.rect(4, y, 10 if y != 11 else 7, 1, PAPER_LO)
    b.rect(10, 14, 5, 5, WAX)
    b.px(10, 14, WAX_HI)
    b.px(14, 18, WAX_LO)
    b.px(12, 16, TRIM)
    return to_image(b)


@lru_cache(maxsize=32)
def ribbon(text: str, hot: bool = False):
    """A crimson banner with forked tails, gold edges and the words in cream; brighter under the pointer."""
    words = text.upper()[:26]
    width = len(words) * 4 + 20
    b = Buf(width, 13)
    body, lo = (RIBBON_HI, RIBBON) if hot else (RIBBON, RIBBON_LO)
    for x, dy in ((0, 0), (1, 1), (2, 2)):
        b.rect(x, 2 + dy, 1, 9 - 2 * dy, lo)
        b.rect(width - 1 - x, 2 + dy, 1, 9 - 2 * dy, lo)
    b.rect(3, 1, width - 6, 11, body)
    b.rect(3, 1, width - 6, 1, TRIM)
    b.rect(3, 11, width - 6, 1, TRIM_LO)
    b.rect(5, 4, 5, 4, PAPER)
    b.px(7, 6, WAX)
    b.px(5, 4, PAPER_LO)
    t35(b, 13, 4, words, INK, sh=RIBBON_LO)
    return to_image(b)


def note(width: int, height: int):
    """The opened decision: a parchment sheet with rolled ends and a wax seal; text is drawn over it by Tk."""
    b = Buf(width, height)
    b.rect(4, 6, width - 8, height - 12, PAPER)
    for y in range(6, height - 6, 7):
        b.rect(6, y, width - 12, 1, PAPER_HI, 0.35)
    for y0 in (0, height - 8):
        b.rect(1, y0 + 1, width - 2, 6, PAPER_LO)
        b.rect(1, y0 + 1, width - 2, 1, PAPER_HI)
        b.rect(1, y0 + 6, width - 2, 1, (120, 96, 60))
        b.rect(0, y0 + 2, 1, 4, (120, 96, 60))
        b.rect(width - 1, y0 + 2, 1, 4, (120, 96, 60))
    for x in (4, width - 5):
        b.rect(x, 6, 1, height - 12, PAPER_LO)
    cx, cy = width - 22, height - 24
    for y in range(-7, 8):
        for x in range(-7, 8):
            d = math.hypot(x, y) / 7
            if d <= 1:
                b.px(cx + x, cy + y, WAX_HI if d < 0.3 and x < 0 else WAX if d < 0.8 else WAX_LO)
    b.rect(cx - 2, cy + 7, 2, 6, RIBBON)
    b.rect(cx + 1, cy + 7, 2, 7, RIBBON_LO)
    return to_image(b)
