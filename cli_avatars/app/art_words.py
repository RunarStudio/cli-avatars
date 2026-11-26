"""FONT.1: words on the pixel-art boards in the chosen face, drawn after the 1x frame is scaled up.

The kit art keeps its pixels: a renderer builds the frame at 1x sized for the words, scales it with NEAREST,
then writes the words at full resolution, so the letters stay smooth and readable at every board scale.
"""

from __future__ import annotations

from math import ceil

import text_fonts as fonts


def face(pt: int = 8, bold: bool = False):
    return fonts.pil_font(fonts.px(pt), bold)


def width(text: str, font) -> int:
    return fonts.measure(text, font)


def line(font) -> int:
    """Line height near 1.4 of the size: room between lines without a gappy board."""
    return round(font.size * 1.4)


def cells(n: float, scale: int) -> int:
    """1x pixels that hold ``n`` final pixels."""
    return ceil(n / scale)


def up(image, scale: int):
    from PIL import Image

    return image if scale <= 1 else image.resize((image.width * scale, image.height * scale), Image.NEAREST)


def write(image, x: int, y: int, text: str, fill, font, shadow=None, align: str = "l", box: int = 0) -> int:
    """``text`` at ``x`` (left, centre or right by ``align``), vertically centred in ``box`` px from ``y``."""
    from PIL import ImageDraw

    w = width(text, font)
    x = x - w // 2 if align == "c" else x - w if align == "r" else x
    if box:
        ascent, descent = font.getmetrics()
        y += (box - ascent - descent) // 2
    fonts.draw(ImageDraw.Draw(image), (x, y), text, _rgb(fill), font, _rgb(shadow) if shadow else None)
    return w


def wrap(text: str, font, room: int, lines: int) -> list[str]:
    """Words packed into lines no wider than ``room`` px, at most ``lines``; the last one ends with an ellipsis."""
    out: list[str] = []
    for word in str(text).split():
        if out and width(out[-1] + " " + word, font) <= room:
            out[-1] += " " + word
            continue
        while width(word, font) > room and len(word) > 1:
            cut = max(1, len(word) - 1)
            while cut > 1 and width(word[:cut], font) > room:
                cut -= 1
            out.append(word[:cut])
            word = word[cut:]
        out.append(word)
    out = out or [""]
    if len(out) > lines:
        out = out[:lines]
        while out[-1] and width(out[-1] + "…", font) > room:
            out[-1] = out[-1][:-1]
        out[-1] = out[-1].rstrip() + "…"
    return out


def _rgb(colour):
    return tuple(colour) if isinstance(colour, (tuple, list)) else colour
