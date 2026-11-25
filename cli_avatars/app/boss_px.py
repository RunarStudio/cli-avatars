"""BACKLOG-BOSS pixel engine: a Torch Ink frame (1-px ink outline, 3-tone ramps, torch rim from the right)."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image


def _hx(s: str) -> tuple[int, int, int]:
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


PAL = {
    k: [_hx(c) for c in v.split()]
    for k, v in {
        "ink": "130f1e 130f1e 130f1e",
        "red": "6a1a3a c0303a f0684a",
        "gold": "8a5424 d99b21 ffd073",
        "iron": "251d3a 4a4470 7a7aa8",
        "bone": "8a80b0 d9d0e8 ffffff",
        "leather": "3b2616 6e4628 a8743f",
        "fire": "e8643c ffb05a fff4c0",
    }.items()
}
RIM = _hx("ffd073")
LIGHT = (0.50, -0.62, 0.60)
THRESHOLDS = (0.42, 0.80)


class Frame:
    """One sprite frame: parts are shaded as they are drawn, ``image`` adds the rim light and the outline."""

    def __init__(self, w: int, h: int | None = None) -> None:
        h = h or w
        self.w, self.h = w, h
        self.rgb = np.zeros((h, w, 3), np.uint8)
        self.a = np.zeros((h, w), bool)
        self.mat = np.full((h, w), "", dtype=object)
        self.norim = np.zeros((h, w), bool)
        yy, xx = np.mgrid[0:h, 0:w]
        self.X, self.Y = xx + 0.5, yy + 0.5

    def ell(self, cx, cy, rx, ry):
        dx, dy = (self.X - cx) / rx, (self.Y - cy) / ry
        d2 = dx * dx + dy * dy
        return d2 <= 1, dx, dy, np.sqrt(np.clip(1 - d2, 0, 1))

    def cap(self, x0, y0, x1, y1, r):
        vx, vy = x1 - x0, y1 - y0
        t = np.clip(((self.X - x0) * vx + (self.Y - y0) * vy) / max(vx * vx + vy * vy, 1e-6), 0, 1)
        dx, dy = (self.X - x0 - t * vx) / r, (self.Y - y0 - t * vy) / r
        d2 = dx * dx + dy * dy
        return d2 <= 1, dx, dy, np.sqrt(np.clip(1 - d2, 0, 1))

    def poly(self, pts, bulge=0.75):
        inside = np.zeros((self.h, self.w), bool)
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            if y0 == y1:
                continue
            inside ^= ((y0 > self.Y) != (y1 > self.Y)) & (self.X < (x1 - x0) * (self.Y - y0) / (y1 - y0) + x0)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        dx = (self.X - cx) / max((max(xs) - min(xs)) / 2, 0.5) * bulge
        dy = (self.Y - cy) / max((max(ys) - min(ys)) / 2, 0.5) * bulge
        return inside, dx, dy, np.sqrt(np.clip(1 - dx * dx - dy * dy, 0.05, 1))

    def part(self, shape, mat, bias=0.0, seam=True, flat=None, norim=False):
        """Draw a shaded part; ``seam`` darkens the pixels it overlaps the edge of."""
        mask, nx, ny, nz = shape
        if not mask.any():
            return
        ramp = PAL[mat]
        lum = np.clip(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2], 0, 1) * 0.85 + 0.15 + bias
        idx = np.full(mask.shape, flat) if flat is not None else sum((lum > t).astype(int) for t in THRESHOLDS)
        idx = np.clip(idx, 0, len(ramp) - 1)
        if seam:
            ring = self.grow(mask) & ~mask & self.a
            for y, x in zip(*np.nonzero(ring), strict=True):
                self.rgb[y, x] = PAL[self.mat[y, x]][0]
        cols = np.array(ramp, np.uint8)[idx]
        self.rgb[mask] = cols[mask]
        self.a |= mask
        self.mat[mask] = mat
        self.norim[mask] = norim

    @staticmethod
    def grow(m):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        return g

    def px(self, pts, mat, tone=-1, norim=True):
        """Set single pixels to one ramp tone of a material."""
        col = PAL[mat][tone]
        for x, y in pts:
            x, y = math.floor(x + 0.5), math.floor(y + 0.5)
            if 0 <= x < self.w and 0 <= y < self.h:
                self.rgb[y, x] = col
                self.a[y, x] = True
                self.mat[y, x] = mat
                self.norim[y, x] = norim

    def E(self, cx, cy, rx, ry, mat, **kw):
        self.part(self.ell(cx, cy, rx, ry), mat, **kw)

    def C(self, x0, y0, x1, y1, r, mat, **kw):
        self.part(self.cap(x0, y0, x1, y1, r), mat, **kw)

    def P(self, pts, mat, bulge=0.75, **kw):
        self.part(self.poly(pts, bulge), mat, **kw)

    def sym(self, pts, mat, tone=-1, norim=True):
        self.px(list(pts) + [(self.w - 1 - x, y) for x, y in pts], mat, tone, norim)

    def line(self, x0, y0, x1, y1, mat, tone=-1, norim=True):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        self.px(
            [(x0 + (x1 - x0) * i / max(n - 1, 1), y0 + (y1 - y0) * i / max(n - 1, 1)) for i in range(n)],
            mat,
            tone,
            norim,
        )

    def image(self, outline=True) -> Image.Image:
        a, rgb = self.a.copy(), self.rgb.copy()
        right = a.copy()
        right[:, :-1] &= ~a[:, 1:]
        for y, x in zip(*np.nonzero(right & ~self.norim), strict=True):
            ramp = PAL[self.mat[y, x]]
            cur = tuple(int(c) for c in rgb[y, x])
            i = ramp.index(cur) if cur in ramp else 2
            rgb[y, x] = ramp[i + 1] if i < 2 else (RIM if self.mat[y, x] != "ink" else cur)
        if outline:
            edge = self.grow(a) & ~a
            rgb[edge] = PAL["ink"][0]
            a |= edge
        out = np.zeros((self.h, self.w, 4), np.uint8)
        out[..., :3] = rgb
        out[..., 3] = a * 255
        out[~a] = 0
        return Image.fromarray(out, "RGBA")
