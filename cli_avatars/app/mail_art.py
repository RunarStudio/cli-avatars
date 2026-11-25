"""MAILROOM art: the room on the Dungeon wall, drawn in code. No Tk.

A pigeonhole shelf whose cubbies fill with letters as the count grows, a burlap mail sack on the flagstones
with letters peeking out, a sorting board for the slips, and parchment slips. Painted at half size and scaled
2x nearest like the dungeon kit; noise comes from fixed seeds, so the same input gives the same image.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from cli_avatars.app.recap_art import GOLD, IRON, PX, WOOD, _wall

COLS, ROWS, PER_CUBBY = 3, 4, 4
CUBBY_W, CUBBY_H = 30, 18
PAPER = (232, 216, 178)
PAPER_DARK = (190, 168, 124)
WAX = ((122, 24, 44), (176, 40, 62), (226, 104, 110))
BURLAP = ((70, 52, 32), (112, 86, 52), (146, 116, 72), (88, 66, 40))
FLAG = ((30, 26, 34), (38, 33, 42), (24, 21, 28))
SHELF_W = COLS * (CUBBY_W + 2) + 6


def layout(width: int, height: int) -> dict:
    """Canvas boxes: ``shelf``, ``sack``, ``plaque`` (the room), ``board`` (where the slips hang)."""
    w, h = max(160, width // PX), max(120, height // PX)
    side = int(min(max(w * 0.3, SHELF_W + 24), 240))
    sx = max(8, (side - SHELF_W) // 2)
    shelf = (sx, 30, sx + SHELF_W, 30 + ROWS * (CUBBY_H + 2) + 6)
    floor = int(h * 0.8)
    top = max(shelf[3] + 40, floor - 48)
    sack = (sx + 10, top, sx + 10 + 46, top + 44)
    plaque = (sx + 8, 10, sx + SHELF_W - 8, 24)
    board = (side + 6, 10, w - 8, h - 8)
    torch = (sx + SHELF_W - 14, shelf[3] + 18)

    def scale(box):
        return tuple(v * PX for v in box)

    return {"shelf": scale(shelf), "sack": scale(sack), "plaque": scale(plaque), "board": scale(board),
            "torch": (torch[0] * PX, torch[1] * PX),
            "floor": floor * PX, "size": (w * PX, h * PX)}


@lru_cache(maxsize=4)
def room(width: int, height: int) -> Image.Image:
    """Wall, flagstones, the empty shelf, the sorting board and the plaque's brass plate."""
    w, h = max(160, width // PX), max(120, height // PX)
    img = np.zeros((h, w, 3), np.uint8)
    _wall(img)
    box = {k: tuple(v // PX for v in b) if isinstance(b, tuple) and len(b) == 4 else b
           for k, b in layout(width, height).items()}
    _flags(img, box["floor"] // PX)
    _board(img, *box["board"])
    _shelf(img, *box["shelf"])
    _brass(img, *box["plaque"])
    _torch(img, *(v // PX for v in box["torch"]))
    out = Image.fromarray(img, "RGB")
    return out.resize((w * PX, h * PX), Image.NEAREST)


@lru_cache(maxsize=48)
def letters(count: int) -> Image.Image:
    """The letters in the shelf's cubbies for ``count``: one per cubby first, then stacking up to four each."""
    w, h = SHELF_W, ROWS * (CUBBY_H + 2) + 6
    img = np.zeros((h, w, 4), np.uint8)
    rng = np.random.default_rng(13)
    n = min(count, COLS * ROWS * PER_CUBBY)
    for at in range(n):
        layer, cubby = divmod(at, COLS * ROWS)
        row, col = divmod(cubby, COLS)
        x = 4 + col * (CUBBY_W + 2) + 2 + int(rng.integers(0, 3))
        y = 4 + row * (CUBBY_H + 2) + CUBBY_H - 7 - layer * 3
        _envelope(img, x, y, CUBBY_W - 6, 6, bool(rng.integers(0, 2)))
    return Image.fromarray(img, "RGBA").resize((w * PX, h * PX), Image.NEAREST)


@lru_cache(maxsize=8)
def sack(count: int) -> Image.Image:
    """A burlap sack tied with rope; with letters waiting, envelopes peek from its mouth."""
    w, h = 46, 44
    img = np.zeros((h, w, 4), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    body = ((xx - w / 2) / (w / 2 - 1)) ** 2 + ((yy - 28) / 16) ** 2 <= 1.0
    neck = (np.abs(xx - w / 2) <= 8 - (yy - 6) * 0.1) & (yy >= 6) & (yy <= 16)
    shape = body | neck
    rng = np.random.default_rng(29)
    weave = ((xx.astype(int) + yy.astype(int)) % 3 == 0) | ((xx.astype(int) - yy.astype(int)) % 4 == 0)
    tone = np.where(weave, 1, 2) + (rng.random((h, w)) < 0.08)
    shade = np.clip(1.15 - ((xx - w * 0.38) / w) ** 2 * 2.6 - ((yy - 22) / h) ** 2 * 0.8, 0.45, 1.15)
    for y in range(h):
        for x in range(w):
            if shape[y, x]:
                base = np.array(BURLAP[min(3, int(tone[y, x]))], np.float32) * shade[y, x]
                img[y, x] = (*np.clip(base, 0, 255).astype(np.uint8), 255)
    img[15:18, 14:32] = (*WOOD[3], 255)
    img[16, 14:32] = (*WOOD[2], 255)
    img[17:22, 30:33] = (*WOOD[3], 255)
    if count:
        for i, x in enumerate((15, 20, 25)[:min(3, count)]):
            _envelope(img, x, 2 + i % 2, 9, 8, i % 2 == 0, upright=True)
    return Image.fromarray(img, "RGBA").resize((w * PX, h * PX), Image.NEAREST)


@lru_cache(maxsize=32)
def slip(width: int, height: int, tone: str = "new") -> Image.Image:
    """A parchment slip pinned to the board: burnt edges, fibres, a brass pin; ``unsorted`` is greyer."""
    w, h = max(40, width // PX), max(16, height // PX)
    rng = np.random.default_rng(7 + w + h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum.reduce([xx, w - 1 - xx, yy * 1.4, (h - 1 - yy) * 1.4]) / 5.0
    burn = np.clip(1.0 - edge, 0, 1) ** 1.8
    paper = np.array(PAPER if tone == "new" else (196, 190, 172), np.float32)
    dark = np.array((132, 98, 54) if tone == "new" else (110, 104, 92), np.float32)
    colour = paper * (1 - burn[..., None]) + dark * burn[..., None]
    colour += (np.repeat(rng.normal(0, 1, (h, 1)), w, axis=1) * 2.5 + rng.normal(0, 1, (h, w)) * 3.0)[..., None]
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = np.clip(colour, 0, 255).astype(np.uint8)
    img[..., 3] = 255
    bite = rng.integers(0, 2, (h, 2))
    for y in range(h):
        img[y, :bite[y, 0], 3] = 0
        img[y, w - bite[y, 1]:, 3] = 0
    px = w // 2
    img[1:4, px - 1:px + 2, :3] = GOLD[0]
    img[1:3, px - 1:px + 1, :3] = GOLD[1]
    img[1, px - 1, :3] = GOLD[2]
    return Image.fromarray(img, "RGBA").resize((w * PX, h * PX), Image.NEAREST)


@lru_cache(maxsize=8)
def seal(color: str) -> Image.Image:
    """A small wax seal for buttons and the count."""
    from cli_avatars.app.recap_art import seal as wax

    return wax(color, 9)


def _envelope(img: np.ndarray, x: int, y: int, w: int, h: int, red: bool, upright: bool = False) -> None:
    hh, ww = img.shape[:2]
    if x + w > ww or y + h > hh:
        return
    img[y:y + h, x:x + w] = (*PAPER, 255)
    img[y + h - 1, x:x + w] = (*PAPER_DARK, 255)
    img[y:y + h, x + w - 1] = (*PAPER_DARK, 255)
    mid = x + w // 2
    for i in range(min(h - 2, w // 2)):
        if not upright:
            img[y + i, x + i] = (*PAPER_DARK, 255)
            img[y + i, x + w - 1 - i] = (*PAPER_DARK, 255)
    if red:
        img[y + h // 2 - 1:y + h // 2 + 1, mid - 1:mid + 1] = (*WAX[1], 255)
        img[y + h // 2 - 1, mid - 1] = (*WAX[2], 255)


def _flags(img: np.ndarray, top: int) -> None:
    h, w, _ = img.shape
    rng = np.random.default_rng(37)
    for row, y in enumerate(range(top, h, 10)):
        off = (row % 2) * 12
        for x in range(-off, w, 24):
            tone = FLAG[int(rng.integers(0, 2))]
            img[y + 1:y + 9, max(0, x + 1):max(0, x + 23)] = tone
            img[y + 1, max(0, x + 1):max(0, x + 23)] = tuple(v + 10 for v in tone)
    img[top:top + 2, :] = FLAG[2]


def _shelf(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    """A dark wooden frame with a grid of cubbies, lit edges at the top and the left."""
    img[y0 + 3:y1 + 3, x1:x1 + 3] = (img[y0 + 3:y1 + 3, x1:x1 + 3] * 0.4).astype(np.uint8)
    img[y0:y1, x0:x1] = WOOD[1]
    img[y0, x0:x1] = WOOD[2]
    img[y0:y1, x0] = WOOD[2]
    img[y1 - 1, x0:x1] = WOOD[0]
    for row in range(ROWS):
        for col in range(COLS):
            cx, cy = x0 + 4 + col * (CUBBY_W + 2), y0 + 4 + row * (CUBBY_H + 2)
            img[cy:cy + CUBBY_H, cx:cx + CUBBY_W] = (16, 12, 14)
            img[cy, cx:cx + CUBBY_W] = (10, 8, 10)
            img[cy + CUBBY_H, cx - 1:cx + CUBBY_W + 1] = WOOD[2]
            img[cy + CUBBY_H + 1, cx - 1:cx + CUBBY_W + 1] = WOOD[3]
    for x in (x0 + 2, x1 - 4):
        img[y0 + 2:y0 + 4, x:x + 2] = IRON[1]


def _board(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    """The sorting board: oak planks in an iron-cornered frame, a dark inset where the slips are pinned."""
    rng = np.random.default_rng(41)
    img[y0 + 3:y1 + 3, x0 + 3:x1 + 3] = (img[y0 + 3:y1 + 3, x0 + 3:x1 + 3] * 0.45).astype(np.uint8)
    img[y0:y1, x0:x1] = WOOD[3]
    for x in range(x0 + 3, x1 - 3, 12):
        plank = np.array(WOOD[3], np.float32) * (0.82 + 0.16 * rng.random())
        end = min(x1 - 3, x + 12)
        grain = rng.normal(0, 1, (y1 - y0 - 6, 1)) * 3 + rng.normal(0, 1, (y1 - y0 - 6, end - x)) * 1.5
        img[y0 + 3:y1 - 3, x:end] = np.clip(plank + grain[..., None], 0, 255).astype(np.uint8)
        img[y0 + 3:y1 - 3, x] = (np.array(WOOD[0]) * 0.9).astype(np.uint8)
    img[y0, x0:x1] = WOOD[2]
    img[y0:y1, x0] = WOOD[2]
    for cx, cy in ((x0, y0), (x1 - 4, y0), (x0, y1 - 4), (x1 - 4, y1 - 4)):
        img[cy:cy + 4, cx:cx + 4] = IRON[1]
        img[cy + 1, cx + 1] = IRON[2]


def _torch(img: np.ndarray, x: int, y: int) -> None:
    """An iron wall sconce with a flame, and its warm glow on the stones around it."""
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    glow = np.clip(1.0 - np.hypot(xx - x, (yy - y) * 1.15) / 70.0, 0, 1) ** 1.6
    warm = 1 + glow[..., None] * np.array((1.4, 0.8, 0.2), np.float32)
    img[:] = np.clip(img * warm + glow[..., None] * np.array((46, 22, 4), np.float32), 0, 255).astype(np.uint8)
    img[y + 2:y + 12, x:x + 3] = IRON[0]
    img[y + 2:y + 12, x + 1] = IRON[1]
    img[y:y + 3, x - 2:x + 5] = IRON[1]
    img[y + 12:y + 14, x - 1:x + 4] = IRON[0]
    for dy, half, tone in ((-1, 2, (226, 104, 30)), (-3, 2, (255, 168, 48)), (-5, 1, (255, 214, 96)),
                           (-7, 1, (255, 240, 180)), (-8, 0, (255, 250, 220))):
        img[y + dy:y + dy + 2, x + 1 - half:x + 2 + half] = tone


def _brass(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    img[y0:y1, x0:x1] = GOLD[0]
    img[y0 + 1:y1 - 1, x0 + 1:x1 - 1] = (176, 128, 40)
    img[y0 + 1, x0 + 1:x1 - 1] = GOLD[1]
    for x in (x0 + 2, x1 - 4):
        img[y0 + (y1 - y0) // 2, x:x + 2] = IRON[0]
