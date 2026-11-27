"""Pixel engine for the throne room: an RGBA float buffer, 2:1 iso projection, faces and pastes.

A port of the approved preview's drawing helpers, so the room uses the preview's numbers.
"""

from __future__ import annotations

import math

import numpy as np

BG = "#06040b"
INKC = "#0b0714"
STEP = "#6f5ca6"
WALL = "#4a3a74"
TH = 0.3
BAYER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
_HEX: dict[str, tuple[int, int, int]] = {}


def col(c) -> tuple[int, int, int]:
    if not isinstance(c, str):
        return tuple(int(v) for v in c)
    if c not in _HEX:
        _HEX[c] = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    return _HEX[c]


def _round(v: float) -> int:
    return int(math.floor(v + 0.5))


def tone(c, k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, _round(v * k))) for v in col(c))


def mix(a, b, t: float) -> tuple[int, int, int]:
    a, b = col(a), col(b)
    return tuple(_round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def mat(c, kl: float = 0.7, kr: float = 0.48, ke: float | None = None) -> dict:
    return {"t": col(c), "l": tone(c, kl), "r": tone(c, kr), "e": tone(c, ke) if ke else None}


def hash01(n: int) -> float:
    n &= 0xFFFFFFFF
    n = ((n ^ 0x9E3779B9) * 0x85EBCA6B) & 0xFFFFFFFF
    if n & 0x80000000:
        n -= 1 << 32
    n ^= (n & 0xFFFFFFFF) >> 13
    n = ((n & 0xFFFFFFFF) * 0xC2B2AE35) & 0xFFFFFFFF
    return (n % 1000) / 1000


def rng(seed: int):
    """Mulberry32, as in the preview."""
    state = [seed & 0xFFFFFFFF]

    def imul(a, b):
        return (a * b) & 0xFFFFFFFF

    def nxt() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        s = state[0]
        t = imul(s ^ (s >> 15), 1 | s)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return nxt


class Sprite:
    """RGBA pixels with an anchor; ``add`` pastes additively (light pieces)."""

    def __init__(self, data: np.ndarray, ax: int, ay: int, add: bool = False):
        self.data = data.astype(np.float32)
        self.h, self.w = data.shape[:2]
        self.ax, self.ay, self.add = int(ax), int(ay), add


class Buf:
    """Float RGBA buffer, 0-255, with the preview's primitives."""

    def __init__(self, w: int, h: int, ox: float = 0, oy: float = 0, t: int = 16):
        self.w, self.h = w, h
        self.d = np.zeros((h, w, 4), np.float32)
        self.ox, self.oy, self.t = ox, oy, t
        self.mask = np.zeros((h, w), np.uint8)

    def g(self, u: float, v: float, z: float = 0.0) -> tuple[int, int]:
        t = self.t
        return _round(self.ox + (u - v) * t), _round(self.oy + (u + v) * t / 2 - z * t)

    def px(self, x: int, y: int, c, a: float = 1.0) -> None:
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        r, g, b = col(c)
        p = self.d[y, x]
        if not p[3]:
            p[0], p[1], p[2], p[3] = r, g, b, 255 * a
            return
        p[0] += (r - p[0]) * a
        p[1] += (g - p[1]) * a
        p[2] += (b - p[2]) * a
        p[3] += (255 - p[3]) * a

    def rect(self, x: int, y: int, w: int, h: int, c, a: float = 1.0) -> None:
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        r, g, b = col(c)
        blk = self.d[y0:y1, x0:x1]
        empty = blk[..., 3] == 0
        for i, v in enumerate((r, g, b)):
            blk[..., i] = np.where(empty, v, blk[..., i] + (v - blk[..., i]) * a)
        blk[..., 3] = np.where(empty, 255 * a, blk[..., 3] + (255 - blk[..., 3]) * a)

    def line(self, x0, y0, x1, y1, c, a: float = 1.0) -> None:
        x0, y0, x1, y1 = _round(x0), _round(y0), _round(x1), _round(y1)
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        e = dx + dy
        while True:
            self.px(x0, y0, c, a)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * e
            if e2 >= dy:
                e += dy
                x0 += sx
            if e2 <= dx:
                e += dx
                y0 += sy

    def poly(self, pts, c, a: float = 1.0) -> None:
        ys = [p[1] for p in pts]
        for y in range(math.floor(min(ys)), math.ceil(max(ys)) + 1):
            xa, xb, yc = math.inf, -math.inf, y + 0.5
            for i, p in enumerate(pts):
                q = pts[(i + 1) % len(pts)]
                if (p[1] <= yc < q[1]) or (q[1] <= yc < p[1]):
                    x = p[0] + (yc - p[1]) / (q[1] - p[1]) * (q[0] - p[0])
                    xa, xb = min(xa, x), max(xb, x)
            if xa == math.inf:
                continue
            xs, xe = _round(xa), _round(xb)
            if xe > xs:
                self.rect(xs, y, xe - xs, 1, c, a)

    def quad(self, corners, c, a: float = 1.0) -> None:
        self.poly([self.g(*p) for p in corners], c, a)

    def iline(self, p, q, c, a: float = 1.0) -> None:
        a0, b0 = self.g(*p), self.g(*q)
        self.line(a0[0], a0[1], b0[0], b0[1], c, a)

    def box(self, u, v, z, du, dv, dz, m) -> None:
        uu, vv, zz = u + du, v + dv, z + dz
        self.quad([(u, vv, z), (uu, vv, z), (uu, vv, zz), (u, vv, zz)], m["l"])
        self.quad([(uu, v, z), (uu, vv, z), (uu, vv, zz), (uu, v, zz)], m["r"])
        self.quad([(u, v, zz), (uu, v, zz), (uu, vv, zz), (u, vv, zz)], m["t"])
        if m["e"]:
            self.iline((u, vv, zz), (uu, vv, zz), m["e"])
            self.iline((uu, vv, zz), (uu, v, zz), m["e"])

    def spr(self, x: int, y: int, rows, pal, flip: bool = False) -> None:
        h, w = len(rows), len(rows[0])
        x0, y0 = x - (w >> 1), y - h + 1
        for j, row in enumerate(rows):
            for i in range(w):
                ch = row[w - 1 - i if flip else i]
                if ch not in ". " and ch in pal:
                    self.px(x0 + i, y0 + j, pal[ch])

    def floor_fn(self, u0, v0, u1, v1, z, f) -> None:
        """Paint the floor plane; ``f(a, b, x, y)`` returns ``(colour, alpha)`` or None."""
        cs = [self.g(u0, v0, z), self.g(u1, v0, z), self.g(u1, v1, z), self.g(u0, v1, z)]
        xs, ys = [p[0] for p in cs], [p[1] for p in cs]
        t = self.t
        for y in range(min(ys), max(ys) + 1):
            dy = (y + 0.5 - self.oy + z * t) / (t / 2)
            for x in range(min(xs), max(xs) + 1):
                dx = (x + 0.5 - self.ox) / t
                a, b = (dy + dx) / 2, (dy - dx) / 2
                if a < u0 or a >= u1 or b < v0 or b >= v1:
                    continue
                r = f(a, b, x, y)
                if r:
                    self.px(x, y, r[0], r[1])

    def face_fn(self, axis, u, v, z, ln, h, f) -> None:
        """Paint a wall face; ``f(a, h, x, y)`` returns a colour, 0 to erase, or None."""
        if axis == "u":
            cs = [self.g(u, v, z), self.g(u + ln, v, z), self.g(u + ln, v, z + h), self.g(u, v, z + h)]
        else:
            cs = [self.g(u, v, z), self.g(u, v + ln, z), self.g(u, v + ln, z + h), self.g(u, v, z + h)]
        xs, ys = [p[0] for p in cs], [p[1] for p in cs]
        t = self.t
        for y in range(min(ys), max(ys) + 1):
            for x in range(min(xs), max(xs) + 1):
                dx = (x + 0.5 - self.ox) / t
                a = dx + v - u if axis == "u" else u - dx - v
                s = u + a + v if axis == "u" else u + v + a
                hh = s / 2 - (y + 0.5 - self.oy) / t - z
                if a < 0 or a >= ln or hh < 0 or hh >= h:
                    continue
                r = f(a, hh, x, y)
                if r is None:
                    continue
                if isinstance(r, int) and r == 0:
                    if 0 <= x < self.w and 0 <= y < self.h:
                        self.d[y, x] = 0
                else:
                    self.px(x, y, r)

    def shadow(self, cu, cv, z, r) -> None:
        def f(a, b, x, y):
            d = math.hypot(a - cu, b - cv) / r
            return (BG, 0.45) if d < 0.75 or (d < 1 and (x + y) & 1) else None

        self.floor_fn(cu - r, cv - r, cu + r, cv + r, z, f)

    def bricks_l(self, u, v, z, du, dz, c) -> None:
        zz = z + 0.4
        while zz < z + dz - 0.05:
            self.iline((u, v, zz), (u + du, v, zz), c)
            zz += 0.4
        k, zz = 0, z
        while zz < z + dz - 0.05:
            x = u + (0.5 if k % 2 else 0)
            while x < u + du:
                if x > u:
                    self.iline((x, v, zz), (x, v, min(z + dz, zz + 0.4)), c)
                x += 1
            zz += 0.4
            k += 1

    def bricks_r(self, u, v, z, dv, dz, c) -> None:
        zz = z + 0.4
        while zz < z + dz - 0.05:
            self.iline((u, v, zz), (u, v + dv, zz), c)
            zz += 0.4
        k, zz = 0, z
        while zz < z + dz - 0.05:
            y = v + (0.5 if k % 2 else 0)
            while y < v + dv:
                if y > v:
                    self.iline((u, y, zz), (u, y, min(z + dz, zz + 0.4)), c)
                y += 1
            zz += 0.4
            k += 1

    def paste(self, s: Sprite, x: int, y: int, a: float = 1.0, add: bool = False,
              flip: bool = False, lit: bool = False) -> None:
        """Anchor ``s`` at ``(x, y)``. Pasted pixels become opaque; ``lit`` keeps them bright."""
        X, Y = x - s.ax, y - s.ay
        x0, y0, x1, y1 = max(0, X), max(0, Y), min(self.w, X + s.w), min(self.h, Y + s.h)
        if x0 >= x1 or y0 >= y1:
            return
        src = s.data[:, ::-1] if flip else s.data
        src = src[y0 - Y:y1 - Y, x0 - X:x1 - X]
        alpha = src[..., 3:4] / 255.0 * a
        dst = self.d[y0:y1, x0:x1]
        on = alpha[..., 0] > 0
        if s.add or add:
            dst[..., :3] = np.minimum(255, dst[..., :3] + src[..., :3] * alpha)
        else:
            dst[..., :3] = dst[..., :3] + (src[..., :3] - dst[..., :3]) * alpha
            self.mask[y0:y1, x0:x1] = np.where(on, 1 if lit else 0, self.mask[y0:y1, x0:x1])
        dst[..., 3] = np.where(on, 255, dst[..., 3])

    def capture(self) -> Sprite:
        """The drawn pixels, cropped, anchored on the iso origin."""
        ys, xs = np.nonzero(self.d[..., 3])
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        return Sprite(self.d[y0:y1 + 1, x0:x1 + 1].copy(), int(self.ox) - x0, int(self.oy) - y0)

    def tex(self, axis, u, v, z, b: "Buf") -> None:
        """A flat bitmap on a wall face, one texel per pixel, reading left to right."""
        bw, bh = b.w, b.h

        def f(a, hh, _x, _y):
            i = min(bw - 1, int(a * 16))
            if axis == "v":
                i = bw - 1 - i
            j = bh - 1 - min(bh - 1, int(hh * 16))
            p = b.d[j, i]
            return (int(p[0]), int(p[1]), int(p[2])) if p[3] else None

        self.face_fn(axis, u, v, z, bw / 16, bh / 16, f)


_F35_SRC = (
    "A010101111101101B110101110101110C011100100100011D110101101101110E111100110100111F111100110100100G011100101101011"
    "H101101111101101I111010010010111J001001001101010K101101110101101L100100100100111M101111111101101N110101101101101"
    "O010101101101010P110101110100100Q010101101110011R110101110101101S011100010001110T111010010010010U101101101101111"
    "V101101101101010W101101111111101X101101010101101Y101101010010010Z111001010100111"
    "0111101101101111101011001001011121100010101001113110001010001110410110111100100151111001100011106011100111101111"
    "711100101001001081111011111011119111101111001110"
    "_000000000000111,000000000010100.000000000000010:000010000010000-000000111000000+000010111010000/001001010100100"
    ">100010001010100=000111000111000?111001010000010"
)
F35 = {_F35_SRC[i]: _F35_SRC[i + 1:i + 16] for i in range(0, len(_F35_SRC), 16)}


def t35(buf: Buf, x: int, y: int, s, c, align: str = "", sh=None, k: int = 1) -> int:
    """3x5 pixel text; ``k`` scales each glyph pixel. Returns the width."""
    s = str(s).upper()
    w = (len(s) * 4 - 1) * k
    if align == "c":
        x -= w >> 1
    elif align == "r":
        x -= w
    for n, ch in enumerate(s):
        g = F35.get(ch)
        if not g:
            continue
        for i in range(15):
            if g[i] != "1":
                continue
            gx, gy = x + (n * 4 + i % 3) * k, y + (i // 3) * k
            if sh is not None:
                buf.rect(gx, gy + k, k, k, sh)
            buf.rect(gx, gy, k, k, c)
    return w


def plate(buf: Buf, x, y, w, h, fill="#120d1f", edge="#4a3a74", hi=None) -> None:
    buf.rect(x + 1, y, w - 2, h, fill)
    buf.rect(x, y + 1, w, h - 2, fill)
    buf.rect(x + 1, y, w - 2, 1, hi or edge)
    buf.rect(x + 1, y + h - 1, w - 2, 1, edge)
    buf.rect(x, y + 1, 1, h - 2, hi or edge)
    buf.rect(x + w - 1, y + 1, 1, h - 2, edge)


def light_pass(buf: Buf, lamps, ambient=(0.35, 0.33, 0.49)) -> None:
    """Ambient plus lamps, multiplied in, dithered to twelfths. Lit pixels keep at least 0.95."""
    h, w = buf.h, buf.w
    acc = np.empty((h, w, 3), np.float32)
    acc[:] = ambient
    for lx, ly, rx, ry, s, c in lamps:
        x0, x1 = max(0, int(lx - rx)), min(w, int(lx + rx) + 1)
        y0, y1 = max(0, int(ly - ry)), min(h, int(ly + ry) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot((xx - lx) / rx, (yy - ly) / ry)
        f = np.where(d < 1, (1 - d) ** 2 * s, 0)[..., None]
        acc[y0:y1, x0:x1] += f * (np.array(col(c), np.float32) / 255)
    yy, xx = np.mgrid[0:h, 0:w]
    th = (np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16)[..., None]
    k = np.minimum(1.3, np.floor(acc * 12 + th) / 12)
    k = np.where(buf.mask[..., None] == 1, np.maximum(k, 0.95), k)
    bg = np.array(col(BG), np.float32)
    keep = np.all(buf.d[..., :3] == bg, axis=-1)[..., None]
    buf.d[..., :3] = np.where(keep, buf.d[..., :3], np.minimum(255, buf.d[..., :3] * k))


def to_image(buf: Buf):
    from PIL import Image

    return Image.fromarray(np.clip(np.floor(buf.d + 0.5), 0, 255).astype(np.uint8), "RGBA")
