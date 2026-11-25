"""HIERARCHY.1 plate: throne -> topic rooms -> task chats -> subagents, each with its chip, model, effort and job.

Drawn in code in the throne room's pixel style (``throne_px``, ``tier_art``) from the default tiers; no AI image.

    python tools/gen_hierarchy_plate.py <out.png> [scale]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from cli_avatars.app import tiers  # noqa: E402
from cli_avatars.app.throne_px import BAYER, Buf, light_pass, mix, plate, t35, to_image, tone  # noqa: E402
from cli_avatars.app.tier_art import chip_buf, glyph  # noqa: E402

W, H = 640, 400
STONE, MORTAR, GOLD, INK, DIM = "#1a1426", "#0c0814", "#e0aa3e", "#f0e6c8", "#9a98b8"
LINES = {
    "main": ("PLANS, SPLITS, DELEGATES", "NEVER DOES THE WORK"),
    "topic": ("TOPIC TO TASKS", "ONE TASK CHAT EACH"),
    "task": ("DOES ONE TASK", "LOOKUPS TO SUBAGENTS"),
    "subagent": ("ONE NARROW JOB", "FAST, CHEAP"),
}
ROWS = (("main", 1, 50), ("topic", 2, 136), ("task", 3, 222), ("subagent", 6, 308))


def wall(b: Buf) -> None:
    """Dark stone courses with dithered mortar, lighter near the top."""
    b.rect(0, 0, W, H, STONE)
    rng = np.random.default_rng(11)
    for row, y in enumerate(range(0, H, 10)):
        off = (row % 2) * 12
        b.rect(0, y, W, 1, MORTAR)
        for x in range(-off, W, 24):
            b.rect(x, y, 1, 10, MORTAR)
            shade = 0.85 + rng.random() * 0.3
            b.rect(x + 1, y + 1, 23, 9, tone(STONE, shade))
            b.rect(x + 1, y + 1, 23, 1, tone(STONE, shade * 1.25))
    yy, xx = np.mgrid[0:H, 0:W]
    fog = (np.array(BAYER, np.float32)[(yy & 3) * 4 + (xx & 3)] / 16 < (yy / H) * 0.55)[..., None]
    b.d[..., :3] = np.where(fog, b.d[..., :3] * 0.7, b.d[..., :3])


def chain(b: Buf, x0: int, y0: int, x1: int, y1: int) -> None:
    """A gold chain of 3x2 links between two plaques."""
    steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / 4))
    for i in range(steps + 1):
        x, y = round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)
        c = GOLD if i % 2 else tone(GOLD, 0.6)
        b.rect(x - 1, y, 3, 2, "#08060c")
        b.rect(x - 1, y - 1, 3, 2, c)


def torch(b: Buf, x: int, y: int) -> None:
    b.rect(x - 1, y, 3, 9, "#4e3018")
    b.rect(x - 2, y - 1, 5, 2, "#8a5a34")
    for dx, dy, c in ((0, -2, "#ffd27a"), (-1, -3, "#f2a33a"), (1, -3, "#f2a33a"), (0, -4, "#fff3c8"),
                      (0, -5, "#f2a33a")):
        b.px(x + dx, y + dy, c)


def plaque(b: Buf, cx: int, top: int, tier: str, rows: dict, wide: int) -> tuple[int, int]:
    """One tier card: glyph, name, where, its chip and two lines of what it does. Returns its top and bottom."""
    chip = tiers.chip(tier, rows)
    h = 58 if wide > 100 else 46
    x = cx - wide // 2
    color = chip["color"]
    plate(b, x, top, wide, h, fill="#120d1f", edge=tone(color, 0.55), hi=color)
    b.rect(x + 2, top + 2, wide - 4, 1, tone(color, 0.35))
    glyph(b, x + 5, top + 5, chip, 2 if wide > 100 else 1)
    name = tiers.NAMES[tier].upper()
    gx = x + (22 if wide > 100 else 14)
    t35(b, gx, top + 5, name, INK, sh="#08060c")
    t35(b, gx, top + 12, tiers.WHERE[tier].upper(), DIM, sh="#08060c")
    tag = chip_buf(chip)
    tx = cx - tag.w // 2
    ty = top + (22 if wide > 100 else 19)
    b.d[ty:ty + tag.h, tx:tx + tag.w] = np.where(tag.d[..., 3:4] > 0, tag.d, b.d[ty:ty + tag.h, tx:tx + tag.w])
    lines = LINES[tier] if wide > 100 else LINES[tier][:1]
    for i, line in enumerate(lines):
        t35(b, cx, ty + tag.h + 4 + i * 8, line, mix(INK, color, 0.25), align="c", sh="#08060c")
    return top, top + h


def render(scale: int = 2):
    rows = tiers.table({})
    b = Buf(W, H)
    wall(b)
    t35(b, W // 2, 10, "THE HIERARCHY", GOLD, align="c", sh="#3e2614", k=2)
    t35(b, W // 2, 24, "STRONG MODELS PLAN, CHEAP ONES RUN ERRANDS", DIM, align="c", sh="#08060c")
    centres: dict[str, list[tuple[int, int, int]]] = {}
    for tier, count, top in ROWS:
        wide = 150 if count <= 3 else 98
        gap = (W - 40) / count
        centres[tier] = []
        for i in range(count):
            cx = round(20 + gap * (i + 0.5))
            if tier == "subagent":
                cx = round(20 + (W - 40) / 3 * (i // 2 + 0.5) + (-51 if i % 2 == 0 else 51))
            centres[tier].append((cx, top, top + (58 if wide > 100 else 46)))
    links = (("main", "topic", lambda i: 0), ("topic", "task", lambda i: 0 if i < 2 else 1),
             ("task", "subagent", lambda i: i // 2))
    for upper, lower, parent in links:
        for i, (cx, top, _bottom) in enumerate(centres[lower]):
            px, _ptop, pbottom = centres[upper][parent(i)]
            chain(b, px, pbottom, cx, top)
    for tier, count, top in ROWS:
        for cx, _top, _bottom in centres[tier]:
            plaque(b, cx, top, tier, rows, 150 if count <= 3 else 98)
    for x in (28, W - 28):
        for y in (70, 230):
            torch(b, x, y)
    t35(b, W // 2, H - 12, "EACH LAUNCH TAKES THE TIER OF WHERE IT STARTS - EDIT CONFIG.JSON CHAT.TIERS",
        mix(DIM, GOLD, 0.3), align="c", sh="#08060c")
    lamps = [(x, y - 4, 70, 60, 0.9, "#f2a33a") for x in (28, W - 28) for y in (70, 230)]
    lamps += [(W // 2, 80, 220, 90, 0.55, "#ffcf4a"), (W // 2, 330, 300, 80, 0.4, "#7fe0ff")]
    light_pass(b, lamps, ambient=(0.62, 0.6, 0.74))
    image = to_image(b)
    return image.resize((W * scale, H * scale), 0) if scale > 1 else image


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "hierarchy.png")
    render(int(sys.argv[2]) if len(sys.argv) > 2 else 2).save(out)
    print(out)
