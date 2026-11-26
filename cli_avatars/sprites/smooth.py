"""SMOOTHANIM: in-between frames drawn from a sheet's own pixels. No blur, no crossfade: each pixel is from a key."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MIN_FRAMES = 8


@dataclass(frozen=True)
class Tune:
    """Hand-tuned per character.

    ``waist``: the breathing and lead line, as a share of the body height from the top of the head.
    ``reach``: px one part may travel between two keys. ``rigid``: share of a part that must land on
    the same colour after its move, else the part changes shape and is taken whole from one key.
    """

    waist: float = 0.55
    reach: int = 3
    rigid: float = 0.55


TUNES = {
    "bubble": Tune(waist=0.5, reach=3),
    "caine": Tune(waist=0.42, reach=3),
    "meowatar": Tune(waist=0.5, reach=4, rigid=0.5),
    "amongo": Tune(waist=0.5, reach=2),
    "bunnylot": Tune(waist=0.45, reach=3),
    "michimaru": Tune(waist=0.5, reach=3),
    "ember_mage": Tune(waist=0.45, reach=3),
    "forest_scout": Tune(waist=0.45, reach=3),
    "frost_wanderer": Tune(waist=0.45, reach=3),
}


def _opaque(a: np.ndarray) -> np.ndarray:
    return a[..., 3] > 0


def _same(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a == b).all(-1) | (~_opaque(a) & ~_opaque(b))


def _dilate(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    pad = np.zeros((h + 2, w + 2), bool)
    pad[1:-1, 1:-1] = mask
    out = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            out |= pad[dy:dy + h, dx:dx + w]
    return out


def _parts(mask: np.ndarray) -> list[np.ndarray]:
    """8-connected parts of a mask, largest first."""
    seen = np.zeros_like(mask)
    h, w = mask.shape
    parts = []
    for y0, x0 in zip(*np.nonzero(mask), strict=True):
        if seen[y0, x0]:
            continue
        part = np.zeros_like(mask)
        stack = [(y0, x0)]
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            part[y, x] = True
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        parts.append(part)
    parts.sort(key=lambda p: -int(p.sum()))
    return parts


def _move(a: np.ndarray, b: np.ndarray, part: np.ndarray, reach: int) -> tuple[tuple[int, int], float]:
    """Whole-pixel move of a part of ``a`` that lands it on the most same-colour pixels of ``b``; move and fit."""
    ys, xs = np.nonzero(part & _opaque(a))
    if not len(ys):
        return (0, 0), 0.0
    h, w = part.shape
    best, best_score = (0, 0), -1.0
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            ty, tx = ys + dy, xs + dx
            inside = (ty >= 0) & (ty < h) & (tx >= 0) & (tx < w)
            hits = (b[ty[inside], tx[inside]] == a[ys[inside], xs[inside]]).all(-1).sum()
            score = float(hits) - 0.01 * (abs(dx) + abs(dy))
            if score > best_score:
                best, best_score = (dx, dy), score
    return best, max(0.0, best_score) / len(ys)


def _half(step: int, lead: bool) -> int:
    """Half a move on whole pixels: a leading part rounds away from zero, a following one toward it."""
    half = abs(step) / 2
    return int(math.copysign(math.ceil(half) if lead else math.floor(half), step))


def body_box(a: np.ndarray) -> tuple[int, int] | None:
    """Top and bottom (exclusive) rows of the visible pixels."""
    rows = np.nonzero(_opaque(a).any(1))[0]
    return (int(rows[0]), int(rows[-1]) + 1) if len(rows) else None


def waist_row(a: np.ndarray, tune: Tune) -> int:
    box = body_box(a)
    if box is None:
        return a.shape[0] // 2
    return box[0] + int(round((box[1] - box[0]) * tune.waist))


def tween(a: np.ndarray, b: np.ndarray, tune: Tune) -> np.ndarray:
    """The frame half-way from key ``a`` to key ``b``.

    Each changed part moves half its own way on whole pixels: across together, and up or down
    with the part above the waist leading and the part below following (1 px of squash or
    stretch). A part that changes shape holds key ``a``; when most of the change is such parts,
    the in-between is ``a`` squashed 1 px, the down beat between two poses.
    """
    diff = ~_same(a, b)
    if not diff.any():
        return a.copy()
    region = _dilate(diff) & (_opaque(a) | _opaque(b))
    out = a.copy()
    out[region] = 0
    waist = waist_row(a, tune)
    h, w = region.shape
    above = np.zeros_like(region)
    above[:waist] = True
    loose = np.zeros_like(region)
    for part in _parts(region):
        (dx, dy), fit = _move(a, b, part, tune.reach)
        if fit < tune.rigid:
            loose |= part
            continue
        for piece, upper in ((part & above, True), (part & ~above, False)):
            ys, xs = np.nonzero(piece & _opaque(a))
            ty, tx = ys + _half(dy, upper), xs + _half(dx, True)
            inside = (ty >= 0) & (ty < h) & (tx >= 0) & (tx < w)
            out[ty[inside], tx[inside]] = a[ys[inside], xs[inside]]
    if loose.sum() * 2 > region.sum():
        return breathe(a, tune, +1)
    out[loose] = a[loose]
    holes = region & ~_opaque(out) & _opaque(a) & _opaque(b)
    out[holes] = b[holes]
    return out


def breathe(a: np.ndarray, tune: Tune, step: int) -> np.ndarray:
    """1 px stretch (``step`` -1, the chest rises) or squash (+1) above the waist; the feet stay."""
    box = body_box(a)
    if box is None or (step < 0 and box[0] == 0):
        return a.copy()
    cut = waist_row(a, tune)
    out = a.copy()
    if step < 0:
        out[0:cut] = a[1:cut + 1]
    else:
        out[1:cut + 1] = a[0:cut]
        out[0] = 0
    return out


def smooth_row(keys: list[np.ndarray], tune: Tune) -> list[np.ndarray]:
    """Keys on even indexes, in-betweens on odd ones; at least ``MIN_FRAMES`` for any row with a key."""
    if not keys:
        return []
    if len(keys) == 1:
        k = keys[0]
        seq = [k, breathe(k, tune, -1), k, breathe(k, tune, +1)]
    elif len(keys) * 2 < MIN_FRAMES:
        seq = list(keys) + [breathe(k, tune, +1) for k in keys]
    else:
        seq = list(keys)
    out = []
    for i, key in enumerate(seq):
        out += [key, tween(key, seq[(i + 1) % len(seq)], tune)]
    return out


def _is_blank(cell: np.ndarray) -> bool:
    return int(cell[..., 3].sum()) < 10


def read_rows(sheet: np.ndarray, fw: int, fh: int) -> list[list[np.ndarray]]:
    """Cells per row, each row stopped at its first blank cell (as ``sprite_loader`` does)."""
    rows = []
    for r in range(sheet.shape[0] // fh):
        cells = []
        for c in range(sheet.shape[1] // fw):
            cell = sheet[r * fh:(r + 1) * fh, c * fw:(c + 1) * fw]
            if _is_blank(cell):
                break
            cells.append(cell.copy())
        rows.append(cells)
    return rows


def smooth_sheet(image, fw: int, fh: int, tune: Tune):
    """A new RGBA sheet of the same cell size with every row smoothed. The source image is not changed."""
    from PIL import Image

    sheet = np.array(image.convert("RGBA"))
    rows = [smooth_row(cells, tune) for cells in read_rows(sheet, fw, fh)]
    cols = max((len(r) for r in rows), default=0)
    out = np.zeros((len(rows) * fh, max(1, cols) * fw, 4), np.uint8)
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            out[r * fh:(r + 1) * fh, c * fw:(c + 1) * fw] = cell
    return Image.fromarray(out, "RGBA")


def palette(image) -> set[tuple[int, int, int, int]]:
    """Every visible RGBA colour of an image."""
    arr = np.array(image.convert("RGBA")).reshape(-1, 4)
    return {tuple(int(v) for v in px) for px in arr[arr[:, 3] > 0]}
