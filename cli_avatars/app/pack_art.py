"""CONTEXT-PACKS art drawn in code: a leather satchel with a brass buckle, and small part icons. No assets."""

from __future__ import annotations

import tkinter as tk

LEATHER = "#5a3a1e"
SATCHEL = (
    "...dddddd...",
    "..d......d..",
    ".LLLLLLLLLL.",
    "LhhhhhhhhhhL",
    "LffffffffffL",
    "LfffGGGGfffL",
    "LlllGYlGlllL",
    "LlllGGGGlllL",
    "LllllllllllL",
    "LllllllllllL",
    ".LLLLLLLLLL.",
)
SCROLL = (
    ".RpppppppR.",
    "RRpwwwwwpRR",
    ".RpppppppR.",
    "..pwwwwwp..",
    "..ppppppp..",
    "..pwwwwp...",
    ".RpppppppR.",
    "RRpppppppRR",
    ".RpppppppR.",
)
GEM = ("..G..", ".GYG.", "GYGGG", ".GGG.", "..G..")
FILE = ("pppp..", "pwwpp.", "pwwwwp", "pwwwwp", "pwwwwp", "pppppp")
LINK = ("..LL..LL", ".L..LL.L", "L..L..L.", ".LL..L..")
PALETTE = {"L": "#3a2412", "l": "#8a5a2b", "h": "#c08a4a", "f": "#9c6630", "d": "#5a3a1e", "G": "#ffcf4a",
           "Y": "#fff2c0", "R": "#6b4a2a", "p": "#d8c8a0", "w": "#8a6a3a"}
PART_ICONS = {"summary": SCROLL, "decisions": GEM, "files": FILE, "links": LINK}


def draw(canvas: tk.Canvas, grid: tuple[str, ...], x: int = 0, y: int = 0, scale: int = 2) -> None:
    """Paint ``grid`` (one character per pixel, ``.`` clear) as rectangles on ``canvas``."""
    for row, line in enumerate(grid):
        for col, char in enumerate(line):
            colour = PALETTE.get(char)
            if colour:
                left, top = x + col * scale, y + row * scale
                canvas.create_rectangle(left, top, left + scale, top + scale, fill=colour, width=0)


def icon(parent, bg: str, grid: tuple[str, ...] = SATCHEL, scale: int = 2) -> tk.Canvas:
    """A canvas just big enough for ``grid``."""
    canvas = tk.Canvas(parent, width=len(grid[0]) * scale, height=len(grid) * scale, bg=bg, highlightthickness=0,
                       bd=0)
    draw(canvas, grid, 0, 0, scale)
    return canvas
