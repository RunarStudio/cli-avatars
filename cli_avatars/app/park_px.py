"""PARK.1 pixel helpers: a small RGBA sprite with an anchor, iso polygons, dark outlines and drop shadows. No Tk.

Sprites sit on the kit's 16x8 iso grid at 1x: ``iso(u, v, z)`` is a point ``u``/``v`` tiles from the sprite's
ground anchor and ``z`` pixels up. The palette is the kit's: night purples, stone greys, warm wood and lamplight.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

HALF_W, HALF_H = 16, 8
SHADOW = (7, 4, 11, 115)
INK = (12, 8, 18, 255)
STONE_D, STONE, STONE_L, STONE_H = (34, 28, 48), (58, 50, 78), (92, 84, 118), (132, 124, 156)
MOSS, MOSS_L = (44, 78, 50), (72, 116, 68)
WOOD_D, WOOD, WOOD_L = (44, 28, 15), (110, 70, 40), (150, 98, 56)
STRAW_D, STRAW, STRAW_L = (118, 92, 46), (170, 138, 74), (206, 178, 106)
IRON_D, IRON, IRON_L = (40, 36, 52), (69, 64, 82), (143, 138, 163)
GLOW, FLAME, AMBER, EMBER = (255, 208, 115), (255, 244, 223), (217, 155, 33), (255, 106, 42)
RUNE = (150, 110, 230)
WATER, WATER_L = (40, 70, 120), (120, 170, 230)


@dataclass
class Sprite:
    image: Image.Image
    ax: int
    ay: int


class Pad:
    """A sprite being drawn: ``w`` by ``h`` with the ground anchor at ``(ax, ay)``."""

    def __init__(self, w: int, h: int, ax: int, ay: int) -> None:
        self.image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.ax, self.ay = ax, ay

    def iso(self, u: float, v: float, z: float = 0.0) -> tuple[float, float]:
        return (self.ax + (u - v) * HALF_W, self.ay + (u + v) * HALF_H - z)

    def poly(self, points, colour) -> None:
        self.draw.polygon([(round(x), round(y)) for x, y in points], fill=_rgba(colour))

    def box(self, u0: float, v0: float, u1: float, v1: float, z0: float, z1: float, top, left, right) -> None:
        """An iso block from height ``z0`` to ``z1``: its two front faces and its top."""
        a, b, c, d = (u0, v1), (u1, v1), (u1, v0), (u0, v0)
        self.poly([self.iso(*a, z0), self.iso(*b, z0), self.iso(*b, z1), self.iso(*a, z1)], left)
        self.poly([self.iso(*b, z0), self.iso(*c, z0), self.iso(*c, z1), self.iso(*b, z1)], right)
        self.poly([self.iso(*a, z1), self.iso(*b, z1), self.iso(*c, z1), self.iso(*d, z1)], top)

    def rect(self, x0: int, y0: int, x1: int, y1: int, colour) -> None:
        self.draw.rectangle((x0, y0, x1, y1), fill=_rgba(colour))

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, colour) -> None:
        self.draw.ellipse((round(cx - rx), round(cy - ry), round(cx + rx), round(cy + ry)), fill=_rgba(colour))

    def line(self, points, colour, width: int = 1) -> None:
        self.draw.line([(round(x), round(y)) for x, y in points], fill=_rgba(colour), width=width)

    def dot(self, x: float, y: float, colour) -> None:
        x, y = round(x), round(y)
        if 0 <= x < self.image.width and 0 <= y < self.image.height:
            self.image.putpixel((x, y), _rgba(colour))

    def shadow(self, rx: float, ry: float, du: float = 0.0) -> None:
        self.ellipse(self.ax + du, self.ay, rx, ry, SHADOW)

    def done(self, outline: bool = True) -> Sprite:
        if outline:
            _outline(self.image)
        return Sprite(self.image, self.ax, self.ay)


def _rgba(colour) -> tuple[int, int, int, int]:
    return tuple(colour) if len(colour) == 4 else (*colour, 255)


def _outline(image: Image.Image) -> None:
    """A dark 1 px rim around every solid pixel, so the piece reads on the dark floor (shadows stay soft)."""
    px = image.load()
    w, h = image.size
    solid = {(x, y) for x in range(w) for y in range(h) if px[x, y][3] == 255}
    for x, y in solid:
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in solid and px[nx, ny][3] < 200:
                px[nx, ny] = INK


def mix(a, b, k: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))


def paste(image: Image.Image, sprite: Sprite, x: float, y: float) -> None:
    """Composite ``sprite`` with its anchor on image pixel ``(x, y)``."""
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    layer.paste(sprite.image, (round(x) - sprite.ax, round(y) - sprite.ay))
    image.alpha_composite(layer)
