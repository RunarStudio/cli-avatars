"""YOU-AVATAR art, drawn in code with Pillow: the keeper (Daniel's avatar), its bubbles, badge and ring.

The keeper is a 40x40 sprite like the roster looks, feet on row 37: a crimson cloak with an ermine collar and gold
trim, a small gold crown, and a lantern on a staff with a steady glow. Two idle frames and four walk frames.
A bubble is a kind-coloured speech balloon with a ``!`` or ``?``; the badge is a red coin with a count.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

SIZE = 40
FEET = 37
INK = (20, 10, 20, 255)
CLOAK, CLOAK_DK, CLOAK_LT = (122, 22, 52, 255), (78, 12, 36, 255), (168, 40, 72, 255)
GOLD, GOLD_LT, GOLD_DK = (232, 178, 64, 255), (255, 238, 160, 255), (150, 98, 30, 255)
TUNIC, SKIN, SKIN_DK = (36, 50, 98, 255), (240, 200, 160, 255), (200, 150, 114, 255)
HAIR, FUR, FUR_DK = (70, 42, 30, 255), (240, 236, 228, 255), (176, 170, 168, 255)
IRON, GLASS, CORE, STAFF = (44, 40, 52, 255), (255, 200, 110, 255), (255, 246, 200, 255), (110, 70, 38, 255)
BOOT = (46, 30, 28, 255)

_GLYPHS = {
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
}
_DIGITS = {
    "0": ("###", "#.#", "#.#", "#.#", "###"), "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"), "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"), "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"), "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"), "9": ("###", "#.#", "###", "..#", "###"),
    "+": ("...", ".#.", "###", ".#.", "..."),
}


def _rgba(hex_colour: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_colour.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _outline(image: Image.Image) -> Image.Image:
    """A one-pixel ink edge around every opaque pixel."""
    src = image.load()
    out = image.copy()
    dst = out.load()
    w, h = image.size
    for y in range(h):
        for x in range(w):
            if src[x, y][3] >= 200:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3] >= 200 and src[nx, ny] != INK:
                    dst[x, y] = INK
                    break
    return out


def _glow(image: Image.Image, at: tuple[int, int], radius: int, strength: float) -> None:
    px = image.load()
    for y in range(max(0, at[1] - radius), min(SIZE, at[1] + radius + 1)):
        for x in range(max(0, at[0] - radius), min(SIZE, at[0] + radius + 1)):
            d = ((x - at[0]) ** 2 + (y - at[1]) ** 2) ** 0.5 / radius
            if d >= 1.0 or px[x, y][3] > 0:
                continue
            a = int(150 * strength * (1.0 - d) ** 2)
            if a > 0:
                px[x, y] = (255, 186, 90, a)


@lru_cache(maxsize=16)
def keeper(frame: int, walking: bool) -> Image.Image:
    """The keeper facing right. ``frame`` 0-3 walks (legs and cloak swing), 0-1 idles (a breath, the lantern)."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = frame % (4 if walking else 2)
    bob = (0, -1, 0, -1)[f] if walking else (0 if f == 0 else -1)
    swing = (-1, 0, 1, 0)[f] if walking else 0
    d.ellipse((11, FEET - 2, 29, FEET + 2), fill=(0, 0, 0, 90))
    # boots
    left, right = (15 + swing, 22 - swing) if walking else (16, 21)
    d.rectangle((left, 33, left + 3, FEET), fill=BOOT)
    d.rectangle((right, 33, right + 3, FEET), fill=BOOT)
    top = 17 + bob
    # cloak: a trapezoid, dark back fold on the left, light fold on the right
    d.polygon([(14, top), (26, top), (29 + swing, 34), (11 + swing, 34)], fill=CLOAK)
    d.polygon([(14, top), (17, top), (15 + swing, 34), (11 + swing, 34)], fill=CLOAK_DK)
    d.polygon([(24, top + 2), (26, top), (29 + swing, 34), (27 + swing, 34)], fill=CLOAK_LT)
    d.line([(11 + swing, 34), (29 + swing, 34)], fill=GOLD)
    # tunic and belt in the cloak's opening
    d.polygon([(19, top + 2), (22, top + 2), (23 + swing // 2, 33), (18 + swing // 2, 33)], fill=TUNIC)
    d.line([(18, top + 2), (18 + swing // 2, 33)], fill=GOLD)
    d.line([(23, top + 2), (23 + swing // 2, 33)], fill=GOLD)
    d.rectangle((15, top + 8, 25, top + 8), fill=GOLD_DK)
    d.point((20, top + 8), fill=GOLD_LT)
    # ermine collar
    d.rectangle((13, top - 1, 27, top + 1), fill=FUR)
    d.line([(13, top + 1), (27, top + 1)], fill=FUR_DK)
    for x in (15, 19, 23, 26):
        d.point((x, top), fill=INK)
    # head
    hy = 9 + bob
    d.rectangle((16, hy, 24, hy + 7), fill=SKIN)
    d.rectangle((16, hy + 6, 24, hy + 7), fill=SKIN_DK)
    d.rectangle((15, hy, 16, hy + 5), fill=HAIR)
    d.rectangle((16, hy - 1, 24, hy), fill=HAIR)
    d.point((22, hy + 3), fill=INK)
    d.point((19, hy + 3), fill=INK)
    d.point((21, hy + 5), fill=SKIN_DK)
    # crown: band, three points, gems
    cy = hy - 2
    d.rectangle((16, cy - 1, 24, cy + 1), fill=GOLD)
    d.line([(16, cy - 1), (24, cy - 1)], fill=GOLD_LT)
    for x in (16, 20, 24):
        d.rectangle((x, cy - 3, x, cy - 2), fill=GOLD)
        d.point((x, cy - 4), fill=GOLD_LT)
    d.point((18, cy), fill=(220, 40, 60, 255))
    d.point((20, cy), fill=(70, 140, 255, 255))
    d.point((22, cy), fill=(220, 40, 60, 255))
    d.rectangle((16, cy + 1, 24, cy + 1), fill=GOLD_DK)
    # arm, staff and lantern on the facing side
    d.rectangle((26, top + 2, 28, top + 6), fill=CLOAK_DK)
    d.rectangle((28, top + 5, 29, top + 6), fill=SKIN)
    sx = 30
    d.line([(sx, 13 + bob), (sx, FEET)], fill=STAFF)
    ly = 11 + bob
    d.rectangle((sx + 1, ly - 1, sx + 5, ly - 1), fill=IRON)
    d.rectangle((sx + 1, ly, sx + 5, ly + 5), fill=IRON)
    d.rectangle((sx + 2, ly + 1, sx + 4, ly + 4), fill=GLASS)
    d.point((sx + 3, ly + 2 + (f % 2)), fill=CORE)
    d.point((sx + 3, ly - 2), fill=IRON)
    img = _outline(img)
    _glow(img, (sx + 3, ly + 2), 8, 1.0)
    return img


def keeper_frame(frame: int, walking: bool, scale: int, mirror: bool) -> Image.Image:
    image = keeper(frame, walking)
    if mirror:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    s = max(1, int(scale))
    return image if s == 1 else image.resize((SIZE * s, SIZE * s), Image.NEAREST)


@lru_cache(maxsize=32)
def bubble(kind_colour: str, glyph: str, scale: int) -> Image.Image:
    """A kind-coloured balloon with a white rim, the glyph in ink and a tail pointing down."""
    w, h = 13, 15
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = _rgba(kind_colour)
    d.rounded_rectangle((0, 0, w - 1, 11), radius=3, fill=INK)
    d.rounded_rectangle((1, 1, w - 2, 10), radius=2, fill=(255, 250, 236, 255))
    d.rounded_rectangle((2, 2, w - 3, 9), radius=2, fill=fill)
    d.polygon([(4, 11), (8, 11), (6, 14)], fill=INK)
    d.polygon([(5, 10), (7, 10), (6, 12)], fill=fill)
    rows = _GLYPHS.get(glyph, _GLYPHS["!"])
    for y, row in enumerate(rows[:5] + rows[6:]):
        for x, c in enumerate(row):
            if c == "#":
                d.point((4 + x, 2 + y + (1 if y >= 5 else 0)), fill=INK)
    s = max(1, int(scale))
    return img if s == 1 else img.resize((w * s, h * s), Image.NEAREST)


@lru_cache(maxsize=32)
def badge(count: int, scale: int) -> Image.Image:
    """A red coin with the count in white (``9+`` past nine)."""
    text = str(count) if count < 10 else "9+"
    w = 4 * len(text) + 5
    img = Image.new("RGBA", (w, 9), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, 8), radius=4, fill=INK)
    d.rounded_rectangle((1, 1, w - 2, 7), radius=3, fill=(214, 52, 74, 255))
    d.line([(3, 1), (w - 4, 1)], fill=(255, 140, 150, 255))
    for i, ch in enumerate(text):
        for y, row in enumerate(_DIGITS[ch]):
            for x, c in enumerate(row):
                if c == "#":
                    d.point((3 + i * 4 + x, 2 + y), fill=(255, 255, 255, 255))
    s = max(1, int(scale))
    return img if s == 1 else img.resize((w * s, 9 * s), Image.NEAREST)


@lru_cache(maxsize=16)
def ring(scale: int) -> Image.Image:
    """The selection ring under the feet: a steady gold iso ellipse."""
    s = max(1, int(scale))
    w, h = 26 * s, 11 * s
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = 200
    d.ellipse((0, 0, w - 1, h - 1), outline=(255, 214, 110, a), width=max(1, s))
    d.ellipse((2 * s, 2 * s, w - 1 - 2 * s, h - 1 - 2 * s), outline=(255, 240, 190, a // 3), width=max(1, s))
    return img
