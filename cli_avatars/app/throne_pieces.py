"""Throne room pieces drawn in code: wall board, banner, door sign, carpets, dais, throne, crystals.

Each is drawn on the preview's iso grid and captured once as a sprite, like the kit's own tiles.
"""

from __future__ import annotations

import math

from cli_avatars.app import throne_model as tm
from cli_avatars.app.throne_px import INKC, STEP, Buf, Sprite, col, mat, mix, t35, tone

GOLD, WINE, PARCH = tm.GOLD, tm.WINE, tm.PARCH
CRYSTAL = ("..o..", ".oWo.", "oWcCo", "oWCCo", "ocCdo", "ocCdo", ".oCdo", ".odo.", "..o..")


def _bitmap(w: int, h: int) -> Buf:
    return Buf(w, h)


def board_bitmap(columns) -> Buf:
    """The board as it hangs on the back wall: five columns, one parchment strip per card."""
    b = _bitmap(144, 38)
    b.rect(0, 0, 144, 38, "#3e2614")
    b.rect(1, 1, 142, 36, "#8a5a34")
    b.rect(1, 1, 142, 1, "#b07a48")
    b.rect(2, 2, 140, 34, "#171022")
    for i, column in enumerate(columns):
        x, c = 2 + i * 28, column.color
        b.rect(x, 2, 28, 7, tone(c, 0.26))
        b.rect(x, 9, 28, 1, tone(c, 0.8))
        t35(b, x + 14, 3, column.label, c, align="c")
        if i:
            b.rect(x, 2, 1, 34, "#3a2c5e")
        for j, card in enumerate(column.cards):
            y = 12 + j * 6
            b.rect(x + 3, y, 23, 5, PARCH)
            b.rect(x + 3, y + 4, 23, 1, "#a8966e")
            b.rect(x + 3, y, 2, 5, c)
            b.rect(x + 7, y + 1, 8 + len(card.title) * 9 // (tm.TITLE_CHARS + 1), 1, "#5a4a36")
            b.rect(x + 7, y + 3, 5 + len(card.who) * 10 // (tm.NAME_CHARS + 1), 1, "#a08c68")
    for x, y in ((1, 1), (142, 1), (1, 36), (142, 36)):
        b.px(x, y, GOLD)
    return b


def banner_bitmap() -> Buf:
    b = _bitmap(15, 40)
    for y in range(40):
        for x in range(15):
            m = min(x, 14 - x)
            if y > 33 and abs(x - 7) < y - 33:
                continue
            if y < 2:
                c = "#8a5a34"
            elif m < 1:
                c = tone(GOLD, 0.7)
            elif m < 2:
                c = GOLD
            elif (x + (y >> 2)) % 5 == 0:
                c = tone(WINE, 0.8)
            else:
                c = WINE
            b.px(x, y, c)
    rows = ("..g.g.g..", "..ggggg..", "..g.g.g..", "...ggg...", ".........", "...gcg...", "..gcCcg..", "...gcg...")
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                b.px(3 + i, 10 + j, GOLD if ch == "g" else "#ffffff" if ch == "C" else "#7df9ff")
    return b


def sign_bitmap() -> Buf:
    b = _bitmap(29, 9)
    b.rect(0, 0, 29, 9, "#8a5a34")
    b.rect(1, 1, 27, 7, "#120d1f")
    b.rect(1, 1, 27, 1, tone(GOLD, 0.6))
    t35(b, 15, 2, "ROOMS", GOLD, align="c")
    return b


def crystal_pal(color: str, dim: bool) -> dict:
    if dim:
        return {"o": INKC, "W": "#8a88a8", "c": "#5c5a78", "C": "#45435e", "d": "#2e2c44"}
    return {"o": INKC, "W": mix(color, "#ffffff", 0.8), "c": mix(color, "#ffffff", 0.4),
            "C": col(color), "d": tone(color, 0.6)}


def rug(b: Buf, u, v, z, du, dv, along_v: bool) -> None:
    def f(a, bb, x, y):
        s = bb - v if along_v else a - u
        w = a - u if along_v else bb - v
        e = min(w, 2 - w)
        t = (s % 1.7) / 1.7
        d = abs(t - 0.5) * 3.4 + abs(w - 1) * 1.9
        if e < 0.07:
            return tone(WINE, 0.55), 1
        if e < 0.17:
            return GOLD, 1
        if e < 0.24:
            return tone(WINE, 0.6), 1
        if abs(d - 0.8) < 0.11:
            return tone(GOLD, 0.85), 1
        if d < 0.34:
            return "#b03a5c", 1
        return (WINE if (x + y) % 2 else tone(WINE, 0.9)), 1

    b.floor_fn(u, v, u + du, v + dv, z, f)


_STONE = mat("#4a3a74", 0.72, 0.5, 1.45)
_DARK = mat("#33274f", 0.72, 0.5, 1.4)
_GOLDM = mat(GOLD, 0.72, 0.52, 1.25)
_STEPM = mat(STEP, 0.66, 0.45, 1.4)


def dais(b: Buf) -> None:
    for k, (du, dv, o) in enumerate(((4.2, 5.2, 0), (3.6, 4.4, 0.4), (3.0, 3.6, 0.8))):
        zz = k * 0.25
        b.box(0, o, zz, du, dv, 0.25, _STEPM)
        b.bricks_l(0, o + dv, zz, du, 0.25, tone(STEP, 0.45))
        b.bricks_r(du, o, zz, dv, 0.25, tone(STEP, 0.3))

    def f(a, bb, x, y):
        e = min(a, 3 - a, bb - 0.8, 4.4 - bb)
        if 0.12 < e < 0.2:
            return GOLD, 0.6
        return ("#33274f", 0.25) if e >= 0.2 and (x + y) % 2 else None

    b.floor_fn(0, 0.8, 3.0, 4.4, 0.75, f)


def carpet(b: Buf) -> None:
    rug(b, 0, 0, 0, 8.4, 2, False)
    k = 0.1
    while k < 2:
        b.iline((0, k, 0), (-0.12, k, 0), GOLD)
        k += 0.2


def throne(b: Buf) -> None:
    b.shadow(1.0, 1.2, 0, 1.3)
    b.box(0, 0.1, 0, 0.35, 2.0, 3.0, _STONE)
    b.box(0, 0.1, 3.0, 0.35, 0.24, 0.4, _STONE)
    b.box(0, 1.86, 3.0, 0.35, 0.24, 0.4, _STONE)
    b.box(0, 0.7, 3.0, 0.35, 0.8, 0.5, _STONE)
    b.box(0, 0.93, 3.5, 0.35, 0.34, 0.32, _GOLDM)

    def back(a, hh, _x, _y):
        m, d = min(a, 2.0 - a), math.hypot(a - 1.0, hh - 2.45)
        if hh < 0.7 or m < 0.12 or hh > 2.9:
            return None
        if d < 0.09:
            return "#ffffff"
        if d < 0.17:
            return "#7df9ff"
        if d < 0.26:
            return GOLD
        if abs(d - 0.42) < 0.04 and hh > 2.3:
            return tone(GOLD, 0.8)
        if m < 0.2 or hh > 2.8 or hh < 0.78:
            return tone(GOLD, 0.8)
        return tone(WINE, 0.68) if (math.floor(a * 8) + math.floor(hh * 8)) % 4 == 0 else tone(WINE, 0.9)

    b.face_fn("v", 0.35, 0.1, 0, 2.0, 3.0, back)
    b.box(0.35, 0.1, 0, 1.2, 0.3, 1.2, _STONE)
    b.box(0.35, 0.4, 0, 1.1, 1.4, 0.6, _DARK)
    b.box(0.35, 0.44, 0.6, 1.06, 1.32, 0.1, mat("#9a2a50", 0.7, 0.5, 1.3))
    b.box(0.35, 1.8, 0, 1.2, 0.3, 1.2, _STONE)
    for o in (0.1, 1.8):
        b.box(1.3, o, 1.2, 0.25, 0.3, 0.14, _GOLDM)
        b.iline((0.35, o + 0.3, 1.2), (1.3, o + 0.3, 1.2), GOLD)
        g = b.g(1.55, o + 0.15, 0.8)
        b.px(g[0], g[1], "#7df9ff")
    b.iline((0.35, 0.1, 3.0), (0.35, 2.1, 3.0), GOLD)


def pedestal(color: str, dim: bool):
    def draw(b: Buf) -> None:
        b.shadow(0.55, 0.55, 0, 0.42)
        b.box(0.28, 0.28, 0, 0.44, 0.44, 0.12, _STEPM)
        b.box(0.36, 0.36, 0.12, 0.28, 0.28, 0.46, mat("#5a4a86", 0.72, 0.5, 1.35))
        b.box(0.3, 0.3, 0.58, 0.4, 0.4, 0.1, _STEPM)
        p = b.g(0.5, 0.5, 0.7)
        b.spr(p[0], p[1], CRYSTAL, crystal_pal(color, dim))

    return draw


def capture(draw) -> Sprite:
    b = Buf(400, 400, 200, 220, 16)
    draw(b)
    return b.capture()
