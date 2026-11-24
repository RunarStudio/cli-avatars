"""Atelier pieces drawn in code: desk, easel, plant, scroll basket, teal rug and the pinned sketches.

Same iso grid and capture as ``throne_pieces``; shapes and colours follow the ATELIER.1 preview.
"""

from __future__ import annotations

import math

from cli_avatars.app import throne_model as tm
from cli_avatars.app.throne_pieces import rug
from cli_avatars.app.throne_px import INKC, Buf, mat, tone

GOLD = tm.GOLD
PAPER, TEAL = "#e6d8b4", "#1f5068"
WOOD, WOODD, AMBER = "#8a5a34", "#5c3a20", "#FFB627"
_WOOD = mat(WOOD, 0.7, 0.5, 1.25)
LEAF = ("....g.G....", ".g..gGG..g.", ".gG.gGg.Gg.", "..gGgGgGg..", "g..gGGGg..G", "gGg.gGg.gGg",
        ".gGggGggGg.", "...gGGGg...", "....gGg....")


def teal_rug(b: Buf) -> None:
    rug(b, 0, 0, 0, 3.4, 2, False, TEAL, "#3a86a0")


def desk(b: Buf) -> None:
    b.shadow(1.2, 0.55, 0, 1.25)
    b.box(0, 0, 0, 2.2, 0.8, 0.72, mat("#6e4526", 0.78, 0.55))
    b.box(-0.06, -0.06, 0.72, 2.32, 0.92, 0.1, _WOOD)
    b.face_fn("u", 0.15, 0.8, 0.1, 1.9, 0.52,
              lambda a, hh, _x, _y: tone(WOODD, 0.9) if abs(a - 0.95) < 0.03 or hh > 0.46 or hh < 0.05 else None)

    def paper(a, bb, x, _y):
        s, t = a - 0.5, bb - 0.1
        ink = abs(math.hypot(s - 0.45, t - 0.3) - 0.2) < 0.05 or (t > 0.5 and 0.1 < s < 0.7 and x % 2)
        return ("#5a4a86" if ink else PAPER), 1

    b.floor_fn(0.5, 0.1, 1.4, 0.72, 0.82, paper)
    j = b.g(0.25, 0.45, 0.82)
    b.rect(j[0] - 1, j[1] - 4, 3, 4, "#5a96ff")
    b.rect(j[0] - 1, j[1] - 5, 3, 1, "#d8c8a0")
    b.px(j[0] - 1, j[1] - 3, "#a8ccff")
    q = b.g(1.5, 0.5, 0.82)
    b.line(q[0], q[1], q[0] + 3, q[1] - 5, "#f4ecff")
    b.px(q[0], q[1], INKC)
    c = b.g(1.9, 0.4, 0.82)
    b.rect(c[0] - 1, c[1] - 1, 3, 2, tone(GOLD, 0.7))
    b.rect(c[0], c[1] - 5, 1, 4, "#efe6d0")
    b.px(c[0], c[1] - 6, "#ffe9a8")
    b.px(c[0], c[1] - 7, AMBER)


def easel(b: Buf) -> None:
    b.shadow(0.5, 0.3, 0, 0.6)
    top = (0.5, 0.1, 2.15)
    b.iline((0.5, -0.45, 0), top, WOODD)
    b.iline((0.05, 0.3, 0), top, WOOD)
    b.iline((0.95, 0.3, 0), top, WOOD)
    b.box(0, 0.2, 0.62, 1, 0.12, 0.07, _WOOD)

    def canvas(a, hh, _x, _y):
        if a < 0.07 or a > 0.81 or hh < 0.07 or hh > 1.08:
            return WOODD
        if math.hypot(a - 0.62, hh - 0.82) < 0.12:
            return "#fff0c0"
        if hh < 0.28 + 0.14 * math.sin(a * 9):
            return "#2f6a58"
        if hh < 0.46 + 0.1 * math.sin(a * 6 + 2):
            return "#4a3a74"
        return "#33274f" if hh > 0.75 else "#7a1f3d"

    b.face_fn("u", 0.06, 0.3, 0.69, 0.88, 1.15, canvas)


def plant(b: Buf) -> None:
    b.shadow(0.5, 0.5, 0, 0.34)
    b.box(0.32, 0.32, 0, 0.36, 0.36, 0.34, mat("#a8553a", 0.72, 0.5, 1.25))
    p = b.g(0.5, 0.5, 0.3)
    b.spr(p[0], p[1], LEAF, {"g": "#2f6a58", "G": "#5adc6e"})


def scrolls(b: Buf) -> None:
    b.shadow(0.5, 0.5, 0, 0.36)
    b.box(0.28, 0.28, 0, 0.44, 0.44, 0.42, mat(WOOD, 0.7, 0.5, 1.25))
    p = b.g(0.5, 0.5, 0.42)
    for k, (dx, h) in enumerate(((-3, 9), (0, 12), (3, 8), (1, 6))):
        b.rect(p[0] + dx, p[1] - h, 2, h, "#c9b98e" if k % 2 == 0 else PAPER)
        b.px(p[0] + dx, p[1] - h, "#fff6dc")
        b.px(p[0] + dx + 1, p[1] - h + 2, "#7a1f3d")


def _doodle(b: Buf, x: int, y: int, k: int) -> None:
    b.rect(x, y, 9, 11, PAPER)
    b.rect(x, y + 10, 9, 1, "#a8966e")
    b.px(x + 4, y, "#e05048")
    if k == 0:
        for i, j in ((2, 3), (3, 2), (4, 2), (5, 3), (5, 4), (4, 5), (3, 5), (2, 4)):
            b.px(x + i + 1, y + j + 1, "#5a4a86")
        b.rect(x + 2, y + 8, 5, 1, "#8a7a5e")
    elif k == 1:
        for i in range(7):
            b.px(x + 1 + i, y + 7 - abs(i - 3), "#2f6a58")
        b.rect(x + 2, y + 3, 2, 2, GOLD)
    elif k == 2:
        b.rect(x + 4, y + 2, 1, 6, "#7a1f3d")
        b.rect(x + 2, y + 4, 5, 1, "#7a1f3d")
        b.rect(x + 3, y + 2, 3, 1, "#7a1f3d")
        b.rect(x + 2, y + 8, 2, 1, "#5a4a36")
        b.rect(x + 5, y + 8, 2, 1, "#5a4a36")
    else:
        for j in range(3):
            b.rect(x + 2, y + 3 + j * 2, 3 + (j * 2) % 3, 1, "#5a4a36")
        b.rect(x + 5, y + 6, 2, 3, "#5a96ff")


def sketches_bitmap() -> Buf:
    """Four sketches pinned on the atelier's back wall."""
    b = Buf(46, 17)
    for x, y, k in ((0, 4, 0), (11, 0, 1), (22, 5, 2), (34, 1, 3)):
        _doodle(b, x, y, k)
    return b


def sketch_bitmap() -> Buf:
    b = Buf(9, 11)
    _doodle(b, 0, 0, 1)
    return b


PIECES = {"desk": desk, "easel": easel, "plant": plant, "scrolls": scrolls, "rug_teal": teal_rug}
