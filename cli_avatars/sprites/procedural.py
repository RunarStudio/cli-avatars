"""Procedural 8×8 fallback sprite. ImageTk is imported inside make_photo."""

import math

from cli_avatars.model.agent import AGENT_STATUS_COLOR, S

_WALK_A = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".L..LL..", "..L.LL..",
]
_WALK_B = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".LL.L...", ".LL..L..",
]


def _parse_sprite(rows, body_rgba, skin_rgba=(255, 200, 150, 255), dark_rgba=(40, 40, 40, 255)):
    from PIL import Image, ImageDraw
    scale = 4
    img = Image.new("RGBA", (8 * scale, 8 * scale), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    for ri, row in enumerate(rows):
        for ci, ch in enumerate(row):
            if ch == ".":
                continue
            color = {"H": skin_rgba, "B": body_rgba, "L": body_rgba, "D": dark_rgba}.get(ch, body_rgba)
            x0, y0 = ci * scale, ri * scale
            dr.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)
    return img


def make_photo(body_hex, status, frame, mirror=False):
    try:
        from PIL import Image, ImageDraw, ImageTk
    except ImportError:
        return None
    br, bg, bb = tuple(int(body_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    body_rgba = (br, bg, bb, 255)
    rows = _WALK_A if frame % 2 == 0 else _WALK_B
    img = _parse_sprite(rows, body_rgba)
    dr = ImageDraw.Draw(img)
    sc = AGENT_STATUS_COLOR.get(status, "#888888")
    sr, sg, sb = tuple(int(sc.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    dr.ellipse([25, 1, 31, 7], fill=(sr, sg, sb, 255))
    if status == S.THINKING:
        oy = int(2 + math.sin(frame * 0.8) * 1.5)
        for i in range(3):
            dr.rectangle([i * 4 + 8, oy, i * 4 + 9, oy + 1], fill=(255, 255, 100, 200))
    if status == S.ERROR:
        dr.line([8, 12, 20, 24], fill=(255, 60, 60, 200), width=2)
        dr.line([20, 12, 8, 24], fill=(255, 60, 60, 200), width=2)
    if status == S.BLOCKED:
        dr.rectangle([27, 0, 30, 4], fill=(32, 24, 8, 255))
        dr.point((28, 6), fill=(32, 24, 8, 255))
    if mirror:
        flip = getattr(getattr(Image, "Transpose", Image), "FLIP_LEFT_RIGHT")
        img = img.transpose(flip)
    return ImageTk.PhotoImage(img)
