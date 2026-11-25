"""REPOS.1 art, drawn in code: the in-use seal of a Repos row and the small repo badge over a room. No Tk.

The seal is a round wax seal pressed with a rune: dark plum and unlit while nobody works in the repo, ember with
a gold rune and a soft halo while someone does. The badge hangs over a room: a dark plate with a gold edge, the lit
seal at its left and the repo's folder name in the 3x5 font; two repos in one room share it, more add ``+n``.
"""

from __future__ import annotations

from cli_avatars.app.throne_px import Buf, t35, to_image, tone

DARK, DARK_HI, DARK_LO = "#3a2c4d", "#4e3d66", "#1c1426"
LIT, LIT_HI, LIT_LO, HALO = "#ff7a1e", "#ffc44a", "#a8340e", "#ffcf4a"
RUNE_DARK, RUNE_LIT = "#5a4a72", "#fff0a0"
PLATE, EDGE, INK, CHAIN = "#171022", "#ffcf4a", "#f0e6c8", "#6a6a80"
RUNE = ("..1..", ".111.", "1.1.1", "..1..", ".1.1.")
NAME_CHARS = 14
MAX_SHOWN = 2


def _seal(b: Buf, x: int, y: int, r: int, lit: bool) -> None:
    mid, hi, lo = (LIT, LIT_HI, LIT_LO) if lit else (DARK, DARK_HI, DARK_LO)
    if lit:
        for dy in range(-r - 3, r + 4):
            for dx in range(-r - 3, r + 4):
                d = (dx * dx + dy * dy) ** 0.5
                if r < d <= r + 3:
                    b.px(x + dx, y + dy, HALO, 0.35 * (1 - (d - r) / 3))
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = (dx * dx + dy * dy) ** 0.5
            if d <= r + 0.4:
                shade = lo if d > r - 1 or dy > r * 0.5 else hi if dx + dy < -r * 0.6 else mid
                b.px(x + dx, y + dy, shade)
    for dx, dy in ((-r, -1), (r, 1), (1, -r), (-1, r)):
        b.px(x + dx, y + dy, lo)
    ink = RUNE_LIT if lit else RUNE_DARK
    for ry, row in enumerate(RUNE):
        for rx, ch in enumerate(row):
            if ch == "1":
                b.px(x - 2 + rx, y - 2 + ry, ink)


def seal_image(lit: bool, size: int = 22):
    """The row's seal at 1x, ``size`` pixels square."""
    b = Buf(size, size)
    _seal(b, size // 2, size // 2, size // 2 - 4, lit)
    return to_image(b)


def label(folder: str) -> str:
    text = str(folder or "").upper()
    return text if len(text) <= NAME_CHARS else text[:NAME_CHARS - 1] + "~"


def badge_image(folders):
    """The badge at 1x: chains, the plate, a lit seal and up to two folder names, then ``+n``."""
    names = [label(f) for f in folders[:MAX_SHOWN]]
    more = len(folders) - len(names)
    text = " / ".join(names) + (f" +{more}" if more else "")
    width = 17 + len(text) * 4 + 4
    b = Buf(width, 18)
    for x in (4, width - 5):
        for y in range(0, 4, 2):
            b.px(x, y, CHAIN)
            b.px(x, y + 1, "#3a3a48")
    b.rect(1, 4, width - 2, 14, tone(EDGE, 0.45))
    b.rect(0, 5, width, 12, tone(EDGE, 0.45))
    b.rect(1, 5, width - 2, 12, EDGE)
    b.rect(2, 6, width - 4, 10, PLATE)
    b.rect(2, 6, width - 4, 1, tone(EDGE, 0.3))
    _seal(b, 9, 11, 4, True)
    t35(b, 16, 9, text, INK, sh="#08060c")
    return to_image(b)
