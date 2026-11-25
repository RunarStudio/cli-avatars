"""HIERARCHY.1 / SUMMON.1 pixels: the tier chips (crown, banner, scroll, spark) and the Summon plate, drawn in code.

Same 3x5 font and plates as the throne room (``throne_px``). No Tk: callers turn the images into photos.
"""

from __future__ import annotations

from cli_avatars.app.throne_px import Buf, t35, to_image, tone

PLATE, EDGE, INK = "#120d1f", "#2a2040", "#f0e6c8"


def glyph(b: Buf, x: int, y: int, chip: dict, k: int = 1) -> None:
    """The tier's 7x5 glyph at ``(x, y)``, each pixel ``k`` wide, with a dark drop shadow."""
    for gy, row in enumerate(chip["rows"]):
        for gx, bit in enumerate(row):
            if bit == "1":
                b.rect(x + gx * k, y + (gy + 1) * k, k, k, "#08060c")
    for gy, row in enumerate(chip["rows"]):
        for gx, bit in enumerate(row):
            if bit == "1":
                lit = gy == 0 or (gy == 1 and gx in (1, 2))
                b.rect(x + gx * k, y + gy * k, k, k, tone(chip["color"], 1.35) if lit else chip["color"])


def label(chip: dict) -> str:
    """``OPUS MEDIUM``: the chip's text in characters the 3x5 font draws."""
    return chip["label"].replace("·", " ").replace("  ", " ")


def chip_buf(chip: dict, k: int = 1) -> Buf:
    """A plate with the glyph and ``MODEL EFFORT``, its rim in the tier's colour."""
    text = label(chip)
    w = (7 + 3 + len(text) * 4 - 1 + 6) * k
    h = 11 * k
    b = Buf(w, h)
    b.rect(0, 0, w, h, chip["color"])
    b.rect(k, k, w - 2 * k, h - 2 * k, PLATE)
    b.rect(k, k, w - 2 * k, k, tone(chip["color"], 0.45))
    glyph(b, 3 * k, 3 * k, chip, k)
    t35(b, (3 + 7 + 3) * k, 3 * k, text, chip["color"], sh="#08060c", k=k)
    return b


def chip_image(chip: dict, k: int = 1):
    return to_image(chip_buf(chip, k))


def summon_buf(k: int = 2) -> Buf:
    """The Summon plate: a gold crown and SUMMON ORCHESTRATOR on a wine plate with gold corners."""
    from cli_avatars.app.tiers import GLYPHS

    crown = {"rows": GLYPHS["main"][2], "color": GLYPHS["main"][1]}
    text = "SUMMON ORCHESTRATOR"
    w, h = (6 + 7 + 4 + len(text) * 4 - 1 + 6) * k, 15 * k
    b = Buf(w, h)
    b.rect(0, 0, w, h, "#3e1424")
    b.rect(k, k, w - 2 * k, h - 2 * k, "#7a1f3d")
    b.rect(2 * k, 2 * k, w - 4 * k, h - 4 * k, "#2a0f1c")
    b.rect(2 * k, 2 * k, w - 4 * k, k, "#a8344f")
    for x, y in ((0, 0), (w - k, 0), (0, h - k), (w - k, h - k)):
        b.rect(x, y, k, k, crown["color"])
    glyph(b, 6 * k, 5 * k, crown, k)
    t35(b, (6 + 7 + 4) * k, 5 * k, text, crown["color"], sh="#08060c", k=k)
    return b


def summon_image(k: int = 2):
    return to_image(summon_buf(k))
