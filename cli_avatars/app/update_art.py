"""UPDATE-BAR.1 art: the update bar drawn in code in the kit's pixel style. No Tk.

A parchment frame with a dark outline round an ink well; the fill is ember (a hot top row, a deep bottom row, a
bright flame at its tip and notches every eight pixels). A failure turns it red; a finished run gilds the corners.
Where a phase reports no progress the fill carries a moving glint (``t`` is the frame number).
"""

from __future__ import annotations

from cli_avatars.app.throne_px import Buf, col, mix, to_image

FRAME, FRAME_HI, FRAME_LO = "#ead9b0", "#fff4d6", "#6b4a26"
WELL, WELL_HI = "#171022", "#241a33"
EMBER, EMBER_HI, EMBER_LO, FLAME = "#ff7a1e", "#ffc44a", "#a8340e", "#fff0a0"
BAD, BAD_HI, BAD_LO = "#c0283c", "#ff6a70", "#6e1020"
GOLD = "#ffcf4a"
GLINT = 7
NOTCH = 8

__all__ = ["bar_image", "col"]


def bar_image(bar, width: int, height: int, t: int = 0):
    """The bar at 1x as a PIL RGBA image, ``width`` by ``height`` pixels (height 8 or more)."""
    b = Buf(width, height)
    b.rect(1, 0, width - 2, height, FRAME_LO)
    b.rect(0, 1, width, height - 2, FRAME_LO)
    b.rect(1, 1, width - 2, height - 2, FRAME)
    b.rect(2, 1, width - 4, 1, FRAME_HI)
    x0, y0, w, h = 3, 3, width - 6, height - 6
    b.rect(x0 - 1, y0 - 1, w + 2, h + 2, FRAME_LO)
    b.rect(x0, y0, w, h, WELL)
    b.rect(x0, y0, w, 1, WELL_HI)
    bad = bar.tone == "bad"
    mid, hi, lo = (BAD, BAD_HI, BAD_LO) if bad else (EMBER, EMBER_HI, EMBER_LO)
    fill = max(0, min(w, round(w * bar.pct / 100)))
    if fill:
        b.rect(x0, y0, fill, h, mid)
        b.rect(x0, y0, fill, 1, hi)
        b.rect(x0, y0 + h - 1, fill, 1, lo)
        for x in range(x0 + NOTCH - 1, x0 + fill - 1, NOTCH):
            b.rect(x, y0 + 1, 1, h - 2, mix(mid, lo, 0.45))
        if bar.tone == "busy":
            b.rect(x0 + fill - 1, y0, 1, h, FLAME)
    if bar.shimmer and fill > 2:
        start = (t * 3) % (fill + 2 * GLINT) - GLINT
        for dx in range(GLINT):
            x = start + dx
            if 0 <= x < fill - 1:
                b.rect(x0 + x, y0 + 1, 1, h - 2, FLAME, 0.55 * (1 - abs(dx - GLINT // 2) / GLINT))
    if bar.tone == "ok":
        for x, y in ((1, 1), (width - 2, 1), (1, height - 2), (width - 2, height - 2)):
            b.px(x, y, GOLD)
    return to_image(b)

