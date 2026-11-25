"""DAILY-RECAP art: the parchment scroll on the Dungeon wall and wax seals, drawn in code. No Tk.

Painted at half size and scaled 2× nearest, so every pixel is a 2×2 block like the dungeon kit.
Same input, same image: noise comes from fixed seeds.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

PX = 2
STONE = (20, 16, 24)
MORTAR = (12, 10, 15)
BRICK = ((34, 28, 40), (30, 25, 36), (38, 31, 44))
PAPER = np.array((226, 208, 164), np.float32)
BURN = np.array((138, 100, 52), np.float32)
WOOD = ((44, 32, 24), (92, 62, 36), (128, 88, 50), (70, 48, 30))
GOLD = ((120, 86, 20), (255, 207, 74), (255, 236, 160))
IRON = ((26, 24, 30), (70, 68, 80), (128, 126, 140))
SEALS = ("#7a1f3d", "#2a4a8a", "#2f6a3a", "#a0661a", "#5a2a7a", "#1f6a6a")
YOU_SEAL = "#c8962a"


def layout(width: int, height: int) -> dict:
    """Canvas boxes of the scroll: ``paper`` (x0, y0, x1, y1) and the readable ``text`` area inside it."""
    w, h = max(80, width // PX), max(80, height // PX)
    margin = max(6, min(28, w // 14))
    top, bottom = 14, h - 12
    paper = (margin, top + 6, w - margin, bottom - 6)
    text = (paper[0] + 14, paper[1] + 8, paper[2] - 14, paper[3] - 6)
    return {"paper": tuple(v * PX for v in paper), "text": tuple(v * PX for v in text),
            "size": (w * PX, h * PX)}


@lru_cache(maxsize=4)
def scroll(width: int, height: int) -> Image.Image:
    """The wall and the hanging scroll for a ``width``×``height`` canvas."""
    w, h = max(80, width // PX), max(80, height // PX)
    img = np.zeros((h, w, 3), np.uint8)
    _wall(img)
    box = layout(width, height)["paper"]
    x0, y0, x1, y1 = (v // PX for v in box)
    _paper(img, x0, y0, x1, y1)
    _rod(img, x0 - 5, x1 + 5, y0 - 6)
    for x in (x0 + 6, x1 - 9):
        _hook(img, x, y0 - 6)
    _rod(img, x0 - 4, x1 + 4, y1, curl=True)
    out = Image.fromarray(img, "RGB")
    return out.resize((w * PX, h * PX), Image.NEAREST)


def seal(color: str, size: int = 7) -> Image.Image:
    """A pixel wax seal: round blob, darker rim, a lit spot, a pressed cross."""
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
    img = np.zeros((size, size, 4), np.uint8)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if d > c + 0.3:
                continue
            shade = 0.6 if d > c - 0.8 else 1.0
            if (x, y) in ((int(c) - 1, int(c) - 1), (int(c) - 2, int(c) - 1)):
                shade = 1.45
            if (x == int(c) and abs(y - c) <= 1) or (y == int(c) and abs(x - c) <= 1):
                shade = 0.72
            img[y, x, :3] = np.clip(rgb * shade, 0, 255)
            img[y, x, 3] = 255
    return Image.fromarray(img, "RGBA").resize((size * PX, size * PX), Image.NEAREST)


def gem(color: str) -> Image.Image:
    """A 4×4 task gem with a lit corner."""
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    for x, y in ((1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (2, 2), (3, 2), (1, 3), (2, 3)):
        img.putpixel((x, y), rgb + (255,))
    img.putpixel((1, 1), (255, 240, 200, 255))
    return img.resize((8, 8), Image.NEAREST)


def seal_color(agent: str) -> str:
    if agent == "daniel":
        return YOU_SEAL
    return SEALS[sum(agent.encode("utf-8")) % len(SEALS)]


def _wall(img: np.ndarray) -> None:
    h, w, _ = img.shape
    img[:] = MORTAR
    rng = np.random.default_rng(5)
    for row, y in enumerate(range(0, h, 8)):
        off = 0 if row % 2 == 0 else 8
        for x in range(-off, w, 16):
            tone = BRICK[int(rng.integers(0, len(BRICK)))]
            img[y + 1:y + 7, max(0, x + 1):max(0, x + 15)] = tone
            img[y + 1, max(0, x + 1):max(0, x + 15)] = tuple(min(255, v + 8) for v in tone)
    grit = rng.random((h, w)) < 0.05
    img[grit] = STONE
    # torchlight: warm in the middle, falling off to the corners
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((xx - w / 2) / (w * 0.62), (yy - h * 0.4) / (h * 0.8))
    light = np.clip(1.25 - d, 0.55, 1.25)
    warm = np.stack([light * 1.08, light, light * 0.86], axis=-1)
    img[:] = np.clip(img * warm, 0, 255).astype(np.uint8)


def _paper(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    h, w = y1 - y0, x1 - x0
    rng = np.random.default_rng(17)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum.reduce([xx, w - 1 - xx, (yy + 4) * 1.6, (h - 1 - yy) * 1.6]) / 10.0
    burn = np.clip(1.0 - edge, 0, 1) ** 1.6
    fibres = np.repeat(rng.normal(0, 1, (h, 1)), w, axis=1) * 3.0 + rng.normal(0, 1, (h, w)) * 4.0
    blotch = np.kron(rng.normal(0, 1, (h // 6 + 1, w // 6 + 1)), np.ones((6, 6)))[:h, :w] * 5.0
    colour = PAPER[None, None, :] * (1 - burn[..., None]) + BURN[None, None, :] * burn[..., None]
    colour += (fibres + blotch)[..., None]
    # ragged side edges: a few pixels bitten off each row
    bite = rng.integers(0, 3, (h, 2))
    area = img[y0:y1, x0:x1]
    keep = np.ones((h, w), bool)
    for y in range(h):
        keep[y, :bite[y, 0]] = False
        keep[y, w - bite[y, 1]:] = False
    area[keep] = np.clip(colour, 0, 255).astype(np.uint8)[keep]
    shadow = img[y0 + 2:y1 + 2, x1:x1 + 2]
    shadow[:] = (shadow * 0.45).astype(np.uint8)


def _rod(img: np.ndarray, x0: int, x1: int, y: int, curl: bool = False) -> None:
    for i, tone in enumerate(WOOD):
        img[y + i, x0:x1] = tone
    img[y + 4, x0:x1] = WOOD[0]
    if curl:
        img[y - 2:y, x0 + 4:x1 - 4] = (178, 150, 104)
        img[y - 1, x0 + 4:x1 - 4] = (150, 116, 70)
    for x in (x0 - 3, x1):
        img[y - 1:y + 6, x:x + 3] = GOLD[0]
        img[y:y + 5, x:x + 3] = GOLD[1]
        img[y + 1, x + 1] = GOLD[2]


def _hook(img: np.ndarray, x: int, y: int) -> None:
    """An iron wall hook: nail head in the mortar, a bar down, a lip curled under the rod."""
    top = max(1, y - 9)
    img[top:y + 6, x:x + 3] = IRON[0]
    img[top:y + 5, x + 1] = IRON[1]
    img[y + 5:y + 7, x - 1:x + 4] = IRON[0]
    img[y + 5, x:x + 3] = IRON[1]
    img[top - 1:top + 2, x - 1:x + 4] = IRON[1]
    img[top - 1, x] = IRON[2]
