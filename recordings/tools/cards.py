"""Drawn in code: a 5x7 pixel font, the title and end cards, chapter plaques, the phone bezel, captions.

Everything is made here or comes from the repo's own kit (Sprites/dungeon_kit, the generic skins). No downloaded art.
"""

from __future__ import annotations

import math
import random
import subprocess  # noqa: TID251 (a recording tool, not the app)
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
NIGHT, INK, GOLD, LIT, WINE = (20, 21, 38), (232, 230, 244), (184, 134, 42), (255, 207, 74), (122, 30, 52)
SKINS = ("ember_mage", "forest_scout", "frost_wanderer")

_G = {  # 5x7 glyphs; accents and the tilde sit on two rows above
    "A": ".###.#...##...#######...##...##...#", "B": "####.#...##...#####.#...##...#####.",
    "C": ".###.#...##....#....#....#...#.###.", "D": "####.#...##...##...##...##...#####.",
    "E": "######....#....####.#....#....#####", "F": "######....#....####.#....#....#....",
    "G": ".###.#...##....#.####...##...#.###.", "H": "#...##...##...#######...##...##...#",
    "I": ".###...#....#....#....#....#...###.", "J": "..###...#....#....#.#..#.#..#..##..",
    "K": "#...##..#.#.#..##...#.#..#..#.#...#", "L": "#....#....#....#....#....#....#####",
    "M": "#...###.###.#.##.#.##...##...##...#", "N": "#...###..##.#.##..###...##...##...#",
    "O": ".###.#...##...##...##...##...#.###.", "P": "####.#...##...#####.#....#....#....",
    "Q": ".###.#...##...##...##.#.##..#..##.#", "R": "####.#...##...#####.#.#..#..#.#...#",
    "S": ".#####....#.....###.....#....#####.", "T": "#####..#....#....#....#....#....#..",
    "U": "#...##...##...##...##...##...#.###.", "V": "#...##...##...##...##...#.#.#...#..",
    "W": "#...##...##...##.#.##.#.##.#.#.#.#.", "X": "#...##...#.#.#...#...#.#.#...##...#",
    "Y": "#...##...#.#.#...#....#....#....#..", "Z": "#####....#...#...#...#...#....#####",
    "0": ".###.#...##..###.#.###..##...#.###.", "1": "..#...##....#....#....#....#...###.",
    "2": ".###.#...#....#...#...#...#...#####", "3": "####.....#....#.###.....#....#####.",
    "4": "...#...##..#.#.#..#.#####...#....#.", "5": "######....####.....#....##...#.###.",
    "6": ".###.#....#....####.#...##...#.###.", "7": "#####....#...#...#...#....#....#...",
    "8": ".###.#...##...#.###.#...##...#.###.", "9": ".###.#...##...#.####....#....#.###.",
    " ": "." * 35, "·": "." * 15 + "..#.." + "." * 15, ":": "....." + "..#.." + "....." * 3 + "..#.." + ".....",
    ".": "." * 30 + "..#..", "-": "." * 15 + "#####" + "." * 15, "¿": "..#.." + "....." + "..#.." + "..#.." +
    ".#..." + "#...#" + ".###.",
}
_ACUTE = ("...#.", "..#..")
_TILDE = (".##.#", "#.##.")
_ACCENTED = {"Á": ("A", _ACUTE), "É": ("E", _ACUTE), "Í": ("I", _ACUTE), "Ó": ("O", _ACUTE), "Ú": ("U", _ACUTE),
             "Ñ": ("N", _TILDE)}


def _rows(ch: str) -> list[str]:
    """Nine rows: two accent rows over the 5x7 glyph."""
    base, top = _ACCENTED.get(ch, (ch, (".....", ".....")))
    g = _G.get(base, _G[" "])
    return [*top, *(g[i:i + 5] for i in range(0, 35, 5))]


def pixel_mask(text: str, px: int, gap: int = 1) -> Image.Image:
    """The text as a 1-bit mask, each font pixel ``px`` screen pixels (nearest neighbour)."""
    text = text.upper()
    w = sum((3 if c == " " else 5) + gap for c in text) - gap
    m = Image.new("L", (max(1, w), 9))
    x = 0
    for c in text:
        rows = _rows(c)
        cw = 3 if c == " " else 5
        for y, row in enumerate(rows):
            for i, bit in enumerate(row[:cw]):
                if bit == "#":
                    m.putpixel((x + i, y), 255)
        x += cw + gap
    return m.resize((m.width * px, m.height * px), Image.NEAREST)


def pixel_text(text: str, px: int, top=LIT, bottom=GOLD, outline=(26, 14, 8), shadow=True) -> Image.Image:
    """Gold pixel lettering: a vertical gradient fill, a half-pixel dark outline and a hard drop shadow."""
    m = pixel_mask(text, 2)
    ring = m.filter(ImageFilter.MaxFilter(3))
    w, h = m.width + 4, m.height + 4
    half = max(1, px // 2)
    out = Image.new("RGBA", (w * half, h * half))
    big = lambda im, dx=2, dy=2: _pad(im, dx, dy, w, h).resize((w * half, h * half), Image.NEAREST)  # noqa: E731
    if shadow:
        out.paste(Image.new("RGBA", out.size, (0, 0, 0, 150)), (0, 0), big(ring, 3, 4))
    out.paste(Image.new("RGBA", out.size, outline + (255,)), (0, 0), big(ring))
    grad = Image.new("RGBA", (1, h))
    for y in range(h):
        k = max(0.0, min(1.0, (y - 6) / max(1, h - 10)))
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)) + (255,))
    out.paste(grad.resize(out.size, Image.NEAREST), (0, 0), big(m))
    return out


def letter_boxes(text: str, px: int, gap: int = 1) -> list[tuple[int, int]]:
    """Left and right edge of each letter inside ``pixel_text(text, px)``."""
    half, x, out = max(1, px // 2), 2, []
    for c in text.upper():
        cw = 3 if c == " " else 5
        out.append(((x - 1) * half, (x + cw * 2 + 1) * half))
        x += (cw + gap) * 2
    return out


def _pad(im, dx, dy, w, h):
    o = Image.new("L", (w, h))
    o.paste(im, (dx, dy))
    return o


@lru_cache(maxsize=8)
def font(size: int) -> ImageFont.FreeTypeFont:
    """Captions: a bold sans with full Spanish accents (Atkinson Hyperlegible is not in the repo)."""
    path = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans:bold"], capture_output=True, text=True).stdout
    return ImageFont.truetype(path or "DejaVuSans-Bold.ttf", size)


@lru_cache(maxsize=16)
def sprite(name: str) -> Image.Image:
    return Image.open(REPO / "Sprites" / name).convert("RGBA")


def walk_frame(skin: str, i: int, scale: int) -> Image.Image:
    """Frame ``i`` of a skin's walk row (row 1, 50 px cells), scaled up crisp."""
    sheet = sprite(f"{skin}.png")
    cell = sheet.width // 6
    f = sheet.crop(((i % 6) * cell, cell, (i % 6 + 1) * cell, 2 * cell))
    return f.resize((cell * scale, cell * scale), Image.NEAREST)


def kit(piece: str, scale: int = 1) -> Image.Image:
    im = sprite(f"dungeon_kit/{piece}.png")
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST) if scale != 1 else im


def ease(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def back_out(k: float) -> float:
    k = max(0.0, min(1.0, k))
    c = 1.9
    return 1 + (c + 1) * (k - 1) ** 3 + c * (k - 1) ** 2


class Card:
    """Title or end card: night sky, embers, a lit kit floor, the generic avatars walking, gold pixel title."""

    def __init__(self, size, title: str, subtitle: str, small: str = "", seed: int = 7, walkers: bool = True):
        self.w, self.h = size
        self.s = self.w / 1920
        self.title, self.subtitle, self.small = title, subtitle, small
        self.walkers = walkers
        rnd = random.Random(seed)
        self.embers = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(0.04, 0.14), rnd.uniform(0, 6.28),
                        rnd.choice((2, 3, 3, 4, 5)), rnd.random()) for _ in range(140)]
        self.stars = [(rnd.uniform(0, 1), rnd.uniform(0, 0.55), rnd.uniform(0, 6.28), rnd.choice((1, 2))) for _ in
                      range(90)]
        self.bg = self._background()
        px = max(4, int(15 * self.s))
        self.word = pixel_text(title, px)
        self.boxes = letter_boxes(title, px)
        self.m = m = int(70 * self.s)
        a = Image.new("L", (self.word.width + 2 * m, self.word.height + 2 * m))
        a.paste(self.word.getchannel("A"), (m, m))
        a = a.filter(ImageFilter.GaussianBlur(int(22 * self.s)))
        gold = [Image.new("L", a.size, c) for c in (255, 170, 60)]
        self.halo = Image.merge("RGBA", (*gold, a.point(lambda v: v // 2)))
        self.sub = self._label(subtitle, int(46 * self.s), INK)
        self.tiny = self._label(small, int(26 * self.s), (190, 176, 140)) if small else None

    def _label(self, text, size, color):
        f = font(size)
        box = f.getbbox(text)
        im = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 12))
        d = ImageDraw.Draw(im)
        d.text((4 - box[0] + 2, 4 - box[1] + 2), text, font=f, fill=(0, 0, 0, 200))
        d.text((4 - box[0], 4 - box[1]), text, font=f, fill=color)
        return im

    def _background(self) -> Image.Image:
        w, h = self.w, self.h
        bg = Image.new("RGB", (w, h))
        top, mid, low = (9, 8, 18), (27, 20, 44), (44, 22, 30)
        d = ImageDraw.Draw(bg)
        for y in range(h):
            k = y / h
            a, b, t = (top, mid, k / 0.6) if k < 0.6 else (mid, low, (k - 0.6) / 0.4)
            d.line([(0, y), (w, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
        floor = Image.new("RGBA", (w, h))
        s = max(2, int(4 * self.s))
        tiles = [kit(n, s) for n in ("b01-losa", "b03-losa-oscura", "b02-losa-clara", "b04-losa-agrietada")]
        tw, th = tiles[0].width, tiles[0].height
        base = int(h * 0.80)
        rnd = random.Random(3)
        for row in range(-1, 6):
            for col in range(-2, w // tw + 3):
                x = col * tw + (tw // 2 if row % 2 else 0)
                y = base + row * th // 2 - th // 2
                floor.alpha_composite(rnd.choice(tiles), (x - tw // 2, y))
        for piece, x in (("b23-antorcha-izq", 0.16), ("b24-antorcha-der", 0.84)):
            t = kit(piece, s)
            floor.alpha_composite(t, (int(w * x - t.width / 2), base - t.height - int(40 * self.s)))
        dim = Image.new("L", (w, h))
        dd = ImageDraw.Draw(dim)
        for y in range(base - th, h):
            dd.line([(0, y), (w, y)], fill=int(150 * max(0.0, 1 - (y - base + th) / (h - base + th)) ** 1.4 + 40))
        floor.putalpha(Image.composite(floor.getchannel("A"), Image.new("L", (w, h)), dim).point(lambda a: a))
        floor.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").array(floor.getchannel("A")),
                                                                   __import__("numpy").array(dim)).astype("uint8")))
        bg.paste(floor, (0, 0), floor)
        vign = Image.new("L", (w, h), 0)
        ImageDraw.Draw(vign).ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.25], fill=255)
        vign = vign.filter(ImageFilter.GaussianBlur(int(120 * self.s)))
        return Image.composite(bg, Image.new("RGB", (w, h), (4, 3, 8)), vign)

    def frame(self, t: float, dur: float) -> Image.Image:
        w, h, s = self.w, self.h, self.s
        im = self.bg.copy().convert("RGBA")
        glow = Image.new("RGBA", (w, h))
        g = ImageDraw.Draw(glow)
        flick = 0.75 + 0.25 * math.sin(t * 11.0) * math.sin(t * 7.3 + 1)
        for x in (0.16, 0.84):
            r = int(260 * s * (0.9 + 0.1 * flick))
            cx, cy = int(w * x), int(h * 0.80 - 120 * s)
            g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 150, 40, int(60 * flick)))
        for sx, sy, ph, sz in self.stars:
            a = int(120 + 110 * math.sin(t * 2.2 + ph))
            g.rectangle([sx * w, sy * h, sx * w + sz * s * 2, sy * h + sz * s * 2], fill=(200, 200, 255, max(0, a)))
        glow = glow.filter(ImageFilter.GaussianBlur(int(40 * s)))
        im.alpha_composite(glow)
        d = ImageDraw.Draw(im)
        for x0, y0, v, ph, sz, hue in self.embers:
            y = (y0 - t * v) % 1.0
            x = x0 + 0.02 * math.sin(t * 1.7 + ph)
            life = math.sin(math.pi * y) ** 0.6
            col = (255, int(120 + 110 * hue), int(40 * hue), int(230 * life))
            px = int(sz * s * 1.6)
            d.rectangle([x * w, y * h * 0.95, x * w + px, y * h * 0.95 + px], fill=col)
        if self.walkers:
            sc = max(2, int(5 * s))
            for i, skin in enumerate(SKINS):
                x = (-0.15 + (t / max(dur, 1)) * 0.5 + i * 0.13) * w
                f = walk_frame(skin, int(t * 9) + i * 2, sc)
                im.alpha_composite(f, (int(x), int(h * 0.80 - f.height + 34 * s)))
        # title: letters drop in, then a shimmer runs through
        total = self.word.width
        x = (w - total) // 2
        y = int(h * 0.30)
        hk = ease((t - 0.8) / 0.8) * (0.8 + 0.2 * math.sin(t * 3.0))
        if hk > 0:
            halo = self.halo.copy()
            halo.putalpha(halo.getchannel("A").point(lambda v: int(v * hk)))
            im.alpha_composite(halo, (x - self.m, y - self.m))
        for i, (l0, l1) in enumerate(self.boxes):
            k = back_out((t - 0.15 - i * 0.07) / 0.55)
            if self.title[i] == " " or k <= 0:
                continue
            L = self.word.crop((l0, 0, l1, self.word.height))
            if k < 1:
                L.putalpha(L.getchannel("A").point(lambda a, k=k: int(a * min(1.0, k * 1.4))))
            im.alpha_composite(L, (x + l0, int(y - (1 - k) * 160 * s)))
        band = (t - 1.25) / 0.9
        if 0 < band < 1:
            sh = Image.new("L", (w, h))
            bx = int(x - 200 * s + band * (total + 400 * s))
            ImageDraw.Draw(sh).polygon([(bx, y - 40), (bx + 60 * s, y - 40), (bx - 60 * s, y + self.word.height + 40),
                                        (bx - 120 * s, y + self.word.height + 40)], fill=150)
            mask = Image.new("L", (w, h))
            mask.paste(self.word.getchannel("A"), (x, y))
            sh = Image.composite(sh, Image.new("L", (w, h)), mask).filter(ImageFilter.GaussianBlur(3))
            im.alpha_composite(Image.merge("RGBA", (*(Image.new("L", (w, h), 255),) * 3, sh)))
        a = ease((t - 0.9) / 0.6)
        if a > 0:
            sub = self.sub.copy()
            sub.putalpha(sub.getchannel("A").point(lambda v: int(v * a)))
            im.alpha_composite(sub, ((w - sub.width) // 2, int(y + self.word.height + 34 * s + (1 - a) * 20 * s)))
        if self.tiny is not None:
            a = ease((t - 1.4) / 0.6)
            tiny = self.tiny.copy()
            tiny.putalpha(tiny.getchannel("A").point(lambda v: int(v * a)))
            im.alpha_composite(tiny, ((w - tiny.width) // 2, int(y + self.word.height + 112 * s)))
        fade = min(ease(t / 0.35), ease((dur - t) / 0.35))
        out = im.convert("RGB")
        return Image.blend(Image.new("RGB", (w, h)), out, fade) if fade < 1 else out


def plaque(text: str, scale: float) -> Image.Image:
    """Chapter plaque: gold pixel text on a night panel with a wine rule, as the kit's door plaques."""
    px = max(2, int(4 * scale))
    word = pixel_text(text, px, shadow=False)
    pad = int(16 * scale)
    w, h = word.width + 2 * pad, word.height + 2 * pad - int(6 * scale)
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=(14, 12, 26, 235), outline=GOLD + (255,), width=max(2, int(3 * scale)))
    d.rectangle([int(6 * scale), h - int(9 * scale), w - int(7 * scale), h - int(6 * scale)], fill=WINE + (255,))
    im.alpha_composite(word, (pad, pad - int(10 * scale)))
    return im


def caption(text: str, width: int, scale: float) -> Image.Image:
    """Burned-in caption: white bold text on a dark box with a gold edge, at most two lines."""
    f = font(int(44 * scale))
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if f.getlength(trial) > width * 0.74 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    lines.append(cur)
    lh = int(58 * scale)
    tw = int(max(f.getlength(ln) for ln in lines))
    pw, ph = int(34 * scale), int(18 * scale)
    w, h = tw + 2 * pw, lh * len(lines) + 2 * ph
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(14 * scale), fill=(10, 9, 18, 214))
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(14 * scale), outline=GOLD + (200,),
                        width=max(1, int(2 * scale)))
    for i, ln in enumerate(lines):
        x = (w - f.getlength(ln)) / 2
        y = ph + i * lh - int(4 * scale)
        d.text((x + 2, y + 2), ln, font=f, fill=(0, 0, 0, 255))
        d.text((x, y), ln, font=f, fill=(255, 255, 255, 255))
    return im


def bezel(screen: tuple[int, int], scale: float) -> tuple[Image.Image, tuple[int, int]]:
    """A phone body drawn around a screen of ``screen`` px; returns the image and the screen's offset."""
    sw, sh = screen
    pad, top = int(16 * scale), int(30 * scale)
    w, h = sw + 2 * pad, sh + top + pad + int(12 * scale)
    im = Image.new("RGBA", (w + 40, h + 40))
    sh_ = Image.new("L", im.size)
    ImageDraw.Draw(sh_).rounded_rectangle([20, 28, w + 20, h + 28], radius=int(52 * scale), fill=190)
    im.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (0, 0), sh_.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([20, 20, w + 20, h + 20], radius=int(52 * scale), fill=(16, 14, 28, 255),
                        outline=GOLD + (255,), width=max(2, int(3 * scale)))
    d.rounded_rectangle([20 + int(70 * scale) + sw // 4, 20 + int(11 * scale), 20 + w - int(70 * scale) - sw // 4,
                         20 + int(19 * scale)], radius=int(4 * scale), fill=(40, 36, 60, 255))
    return im, (20 + pad, 20 + top)
