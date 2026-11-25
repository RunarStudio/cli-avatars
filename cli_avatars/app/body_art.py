"""BODY art drawn in code: posed avatar frames, the bench, the chimney, smoke puffs and the hover tag. No Tk.

Poses bend the avatar's own sheet frame at its native pixels, so every roster look gets them: ``stride`` leans into
the walk with a bob and dust at the heels; ``slump`` folds the legs onto the seat, drops and greys the shoulders and
lets a sigh rise; ``tap`` leans back a pixel and lifts the front foot on the beat with a dust tick. Each takes a
blend ``k`` (0..1) so a change eases in.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from cli_avatars.app.body import IDLE, SLUMP, STRIDE, TAP
from cli_avatars.app.throne_px import Buf, t35, to_image

WOOD, WOOD_HI, WOOD_LO, IRON = (138, 90, 52), (186, 128, 76), (70, 44, 24), (52, 48, 64)
STONE, STONE_HI, STONE_LO = (92, 82, 112), (128, 116, 150), (50, 42, 66)
SMOKE = (206, 196, 224)
SMOKE_W, SMOKE_H = 44, 120
SMOKE_STEPS = 32
PUFFS = 22


def _rows(a: np.ndarray) -> tuple[int, int]:
    """Top and bottom opaque rows (the head's top and the feet)."""
    ys = np.nonzero(a[..., 3].max(axis=1) > 0)[0]
    return (int(ys[0]), int(ys[-1])) if len(ys) else (0, a.shape[0] - 1)


def _cols(a: np.ndarray) -> tuple[int, int]:
    xs = np.nonzero(a[..., 3].max(axis=0) > 0)[0]
    return (int(xs[0]), int(xs[-1])) if len(xs) else (0, a.shape[1] - 1)


def _shift_row(row: np.ndarray, dx: int) -> np.ndarray:
    if dx == 0:
        return row
    out = np.zeros_like(row)
    if dx > 0:
        out[dx:] = row[:-dx]
    else:
        out[:dx] = row[-dx:]
    return out


def _put(a: np.ndarray, x: int, y: int, rgb, alpha: float) -> None:
    if 0 <= y < a.shape[0] and 0 <= x < a.shape[1]:
        p = a[y, x]
        if p[3] == 0:
            p[:3], p[3] = rgb, 255 * alpha
        else:
            p[:3] = p[:3] + (np.array(rgb, np.float32) - p[:3]) * alpha


def stride(a: np.ndarray, k: float, phase: int, face: int) -> np.ndarray:
    """Lean into the walk (head ``2k`` px ahead), bob on the passing steps, dust behind the heels."""
    top, feet = _rows(a)
    span = max(1, feet - top)
    out = np.zeros_like(a)
    for y in range(a.shape[0]):
        out[y] = _shift_row(a[y], face * round(k * 3.0 * (feet - y) / span) if y <= feet else 0)
    if k > 0.5 and phase % 2 == 1:
        out = np.roll(out, -1, axis=0)
        out[-1] = 0
    if k > 0.3:
        left, right = _cols(a)
        heel = left - 1 if face > 0 else right + 1
        for i, (dx, dy) in enumerate(((0, 0), (-2, -1), (-4, 0))):
            _put(out, heel + face * dx - face * (phase % 2), feet - dy, (170, 150, 120), k * 0.55 / (i + 1))
    return out


def slump(a: np.ndarray, k: float, phase: int, face: int) -> np.ndarray:
    """Seated: legs folded to the seat, shoulders dropped and forward, colour drained a little, a sigh rising."""
    top, feet = _rows(a)
    height = feet - top + 1
    hip = top + int(height * 0.62)
    drop = round(k * height * 0.28)
    out = np.zeros_like(a)
    for y in range(top, hip):
        dx = face * round(k * 2.4) if y < top + height * 0.38 else face * round(k * 0.6)
        if 0 <= y + drop < a.shape[0]:
            out[y + drop] = _shift_row(a[y], dx)
    legs = feet - hip + 1
    kept = max(1, legs - drop)
    for i in range(kept):
        src = hip + min(legs - 1, int(i * legs / kept))
        out[hip + drop + i] = np.maximum(out[hip + drop + i], a[src])
    grey = out[..., :3].mean(axis=2, keepdims=True)
    tint = np.array((96, 104, 150), np.float32)
    out[..., :3] = out[..., :3] * (1 - 0.3 * k) + (grey * 0.6 + tint * 0.4) * 0.3 * k
    if k > 0.6:
        step = phase % 8
        if step < 5:
            left, right = _cols(a)
            mouth = (right + 1 if face > 0 else left - 1) - face
            y = top + drop + int(height * 0.25) - step
            for dx, dy in ((0, 0), (face, -1), (0, -2)):
                _put(out, mouth + dx, y + dy, SMOKE, 0.7 * (1 - step / 5))
    return out


def tap(a: np.ndarray, k: float, phase: int, face: int) -> np.ndarray:
    """Weight back a pixel, the front foot up on the beat and down with a dust tick."""
    top, feet = _rows(a)
    span = max(1, feet - top)
    out = np.zeros_like(a)
    for y in range(a.shape[0]):
        out[y] = _shift_row(a[y], -face * round(k * 1.0 * (feet - y) / span) if y <= feet else 0)
    left, right = _cols(out[feet - 3:feet + 1]) if feet >= 3 else (0, a.shape[1] - 1)
    mid = (left + right) // 2
    front = slice(mid + 1, a.shape[1]) if face > 0 else slice(0, mid)
    lift = round(k * 3) if phase % 2 == 0 else 0
    if lift:
        foot = out[feet - 3:feet + 1, front].copy()
        out[feet - 3:feet + 1, front] = 0
        out[feet - 3 - lift:feet + 1 - lift, front] = np.maximum(out[feet - 3 - lift:feet + 1 - lift, front], foot)
        toe = right + 2 if face > 0 else left - 2
        for dy in (0, 2):
            _put(out, toe, feet - lift - dy, (255, 214, 140), 0.75 * k)
            _put(out, toe + face, feet - lift - dy - 1, (255, 214, 140), 0.45 * k)
    elif k > 0.5:
        toe = right + 1 if face > 0 else left - 1
        _put(out, toe, feet, (214, 196, 160), 0.6)
        _put(out, toe + face, feet - 1, (214, 196, 160), 0.35)
    return out


POSERS = {STRIDE: stride, SLUMP: slump, TAP: tap}


def posed(image, pose: str, was: str, k: float, phase: int, face: int):
    """The frame with ``pose`` at ``k`` and the pose before at ``1 - k``; a PIL RGBA image the same size."""
    from PIL import Image

    a = np.asarray(image.convert("RGBA"), np.float32).copy()
    if was != pose and was in POSERS and k < 1.0:
        a = POSERS[was](a, 1.0 - k, phase, face)
    if pose in POSERS and k > 0.0:
        a = POSERS[pose](a, k, phase, face)
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA")


@lru_cache(maxsize=8)
def bench(seats: int):
    """A plank bench along the back wall (the u axis), ``seats`` tiles long; image and its floor anchor."""
    seats = max(2, seats)
    b = Buf(16 * seats + 20, 8 * seats + 22, ox=10, oy=14, t=16)
    length, depth, seat = float(seats), 0.42, 0.5
    for u in (0.12, length - 0.22):
        for v in (0.06, depth - 0.12):
            x, y = b.g(u, v, 0)
            b.rect(x - 1, y - 7, 2, 7, WOOD_LO)
            b.px(x - 1, y - 7, WOOD)
    back = [b.g(0, 0, seat + 0.42), b.g(length, 0, seat + 0.42), b.g(length, 0, seat + 0.18), b.g(0, 0, seat + 0.18)]
    b.poly(back, WOOD_LO)
    b.line(*back[0], *back[1], WOOD)
    top = [b.g(0, 0, seat), b.g(length, 0, seat), b.g(length, depth, seat), b.g(0, depth, seat)]
    b.poly(top, WOOD)
    b.line(*top[3], *top[2], WOOD_HI)
    lip = [b.g(0, depth, seat), b.g(length, depth, seat), b.g(length, depth, seat - 0.09), b.g(0, depth, seat - 0.09)]
    b.poly(lip, WOOD_LO)
    for i in range(1, seats):
        b.line(*b.g(i, 0, seat), *b.g(i, depth, seat), WOOD_LO, 0.6)
    for u in (0.3, length - 0.3):
        b.px(*b.g(u, depth * 0.5, seat), IRON)
    return to_image(b), b.g(0, 0, 0)


def chimney(level: float):
    """A squat stone stack on the wall top with a lit throat; brighter as the run goes on."""
    b = Buf(18, 22)
    b.rect(3, 6, 12, 16, STONE)
    b.rect(3, 6, 2, 16, STONE_HI)
    b.rect(13, 6, 2, 16, STONE_LO)
    for y in (10, 15, 20):
        b.rect(3, y, 12, 1, STONE_LO, 0.7)
    b.rect(1, 3, 16, 3, STONE_HI)
    b.rect(1, 5, 16, 1, STONE_LO)
    b.rect(5, 2, 8, 2, (24, 18, 30))
    b.rect(6, 2, 6, 1, (255, 150, 60), 0.35 + 0.5 * level)
    return to_image(b)


def smoke(level: float, step: int, wind: float = 0.0):
    """Puffs rising from the bottom centre, swaying and swelling as they climb; more and denser with ``level``."""
    b = Buf(SMOKE_W, SMOKE_H)
    count = max(2, round(PUFFS * (0.35 + 0.65 * level)))
    rise = SMOKE_H * (0.55 + 0.45 * level)
    for i in range(count):
        life = ((step / SMOKE_STEPS) + i / count) % 1.0
        y = SMOKE_H - 3 - life * rise
        x = SMOKE_W / 2 + math.sin(life * 5.0 + i * 1.7) * (2 + 7 * life) + wind * life * 10
        r = 2.4 + life * (4.0 + 6.0 * level)
        alpha = (0.35 + 0.5 * level) * min(1.0, life * 6) * (1.0 - life) ** 1.3
        shade = tuple(int(c * (0.78 + 0.22 * (1 - life))) for c in SMOKE)
        _disc(b, x, y, r, shade, alpha)
        _disc(b, x - r * 0.3, y - r * 0.35, r * 0.55, (236, 230, 246), alpha * 0.45)
    if level > 0.0:
        for j in range(3):
            t = ((step * 2 + j * 11) % SMOKE_STEPS) / SMOKE_STEPS
            b.px(int(SMOKE_W / 2 + math.sin(j * 2.3 + t * 6) * 3), int(SMOKE_H - 3 - t * 26), (255, 170, 70),
                 (1 - t) * 0.9)
    return to_image(b)


def _disc(b: Buf, cx: float, cy: float, r: float, rgb, alpha: float) -> None:
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r), int(cx + r) + 1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / max(0.5, r)
            if d <= 1.0:
                b.px(x, y, rgb, alpha * (1.0 - d * d))


TAG_INK = {STRIDE: (150, 230, 140), SLUMP: (150, 160, 220), TAP: (255, 190, 60), IDLE: (200, 196, 216)}


def tag(word: str, pose: str):
    """The one-word state on a dark slate with a pose-coloured rim and pip."""
    width = len(word) * 4 + 12
    b = Buf(width, 11)
    ink = TAG_INK.get(pose, TAG_INK[IDLE])
    b.rect(0, 0, width, 11, (12, 8, 18), 0.92)
    b.rect(0, 0, width, 1, ink, 0.8)
    b.rect(0, 10, width, 1, (0, 0, 0), 0.6)
    b.rect(3, 4, 3, 3, ink)
    t35(b, 9, 3, word, (240, 230, 200), sh=(8, 6, 12))
    return to_image(b)
