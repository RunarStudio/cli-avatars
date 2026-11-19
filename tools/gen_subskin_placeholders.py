#!/usr/bin/env python3
"""Code-generated 32×32 placeholder sheets for subagent skins.

These are not commissioned art. Each sheet is a Stream Avatars grid
(4 columns × 5 rows) drawn with at most six colours, a tiny PH mark,
and ``placeholder: true`` in ``Sprites/subagents/manifest.json``.
TODO(Caine art): replace the PNGs; keep the ids and the mode flag.

    python tools/gen_subskin_placeholders.py
    python tools/gen_subskin_placeholders.py --out Sprites/subagents
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

CELL = 32
COLS = 4
ROWS = 5
# idle, run, sit, stand, jump — same rows as the orchestrator sheets.

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "Sprites" / "subagents"


def put(img: Image.Image, x: int, y: int, colour) -> None:
    if 0 <= x < CELL and 0 <= y < CELL:
        img.putpixel((x, y), colour)


def fill(img: Image.Image, x: int, y: int, w: int, h: int, colour) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            put(img, xx, yy, colour)


def stamp_ph(img: Image.Image, ink) -> None:
    """Tiny PH in the top-left, in a colour the sheet already uses."""
    glyph = (
        "###.#.#",
        "#.#.#.#",
        "###.###",
        "#...#.#",
        "#...#.#",
    )
    for y, row in enumerate(glyph):
        for x, ch in enumerate(row):
            if ch == "#":
                put(img, 1 + x, 1 + y, ink)


def pose_for(row: int, col: int) -> dict:
    if row == 0:
        return {"dy": col % 2, "phase": 0, "tuck": False, "jump": False}
    if row == 1:
        return {"dy": 0, "phase": col % 2, "tuck": False, "jump": False}
    if row == 2:
        return {"dy": 3, "phase": 0, "tuck": True, "jump": False}
    if row == 3:
        return {"dy": 1 if col == 2 else 0, "phase": 0, "tuck": False, "jump": False}
    return {"dy": -4 if col % 2 == 0 else -2, "phase": 1, "tuck": False, "jump": True}


def _legs(img, x0, y, colour, phase: int, tuck: bool) -> None:
    if tuck:
        fill(img, x0, y, 8, 2, colour)
        return
    lift = 2 if phase else 0
    fill(img, x0, y - lift, 2, 5, colour)
    fill(img, x0 + 5, y - (2 - lift), 2, 5, colour)


def draw_imp(img, pal, pose) -> None:
    ink, body, horn, eye, leg, belly = pal
    y = 9 + pose["dy"]
    fill(img, 11, y, 2, 3, horn)
    fill(img, 18, y, 2, 3, horn)
    fill(img, 11, y + 3, 9, 7, ink)
    fill(img, 12, y + 4, 7, 5, body)
    put(img, 13, y + 6, eye)
    put(img, 16, y + 6, eye)
    fill(img, 12, y + 10, 7, 6, ink)
    fill(img, 13, y + 11, 5, 4, belly)
    _legs(img, 13, y + 16, leg, pose["phase"], pose["tuck"])
    fill(img, 19, y + 12, 4, 2, body)
    put(img, 23, y + 11, horn)


def draw_claude4(img, pal, pose) -> None:
    """Side-on quadruped. Four legs, not a standing person."""
    ink, body, belly, nose, eye, spot = pal
    y = 12 + pose["dy"]
    phase = pose["phase"]
    fill(img, 6, y + 2, 16, 7, ink)
    fill(img, 7, y + 3, 14, 5, body)
    fill(img, 8, y + 6, 8, 2, belly)
    fill(img, 18, y - 2, 7, 7, ink)
    fill(img, 19, y - 1, 5, 5, body)
    put(img, 22, y + 1, eye)
    fill(img, 23, y + 2, 3, 2, nose)
    fill(img, 20, y - 4, 2, 2, spot)
    if pose["tuck"]:
        fill(img, 8, y + 9, 14, 2, ink)
    else:
        for index, x in enumerate((8, 12, 16, 20)):
            lift = 2 if (index % 2) == phase else 0
            fill(img, x, y + 9 - lift, 2, 5, ink)
    tail_y = y + 3 - (2 if phase else 0)
    fill(img, 3, tail_y, 4, 2, body)


def draw_winged_light(img, pal, pose) -> None:
    ink, body, wing, glow, core, spark = pal
    y = 10 + pose["dy"]
    flap = -3 if pose["jump"] or pose["phase"] else 1
    fill(img, 4, y + 6 + flap, 8, 3, wing)
    fill(img, 20, y + 6 + flap, 8, 3, wing)
    fill(img, 6, y + 4 + flap, 4, 2, glow)
    fill(img, 22, y + 4 + flap, 4, 2, glow)
    fill(img, 14, y + 1, 4, 4, glow)
    fill(img, 15, y + 2, 2, 2, spark)
    fill(img, 13, y + 5, 6, 10, ink)
    fill(img, 14, y + 6, 4, 8, body)
    fill(img, 15, y + 8, 2, 3, core)
    if not pose["tuck"]:
        fill(img, 14, y + 15, 2, 4, ink)
        fill(img, 16, y + 15, 2, 4, ink)
    else:
        fill(img, 13, y + 14, 6, 2, ink)


def draw_cat(img, pal, pose) -> None:
    ink, fur, belly, ear, eye, nose = pal
    y = 10 + pose["dy"]
    fill(img, 12, y, 3, 3, ear)
    fill(img, 18, y, 3, 3, ear)
    fill(img, 12, y + 2, 9, 7, ink)
    fill(img, 13, y + 3, 7, 5, fur)
    put(img, 14, y + 5, eye)
    put(img, 18, y + 5, eye)
    put(img, 16, y + 6, nose)
    fill(img, 13, y + 9, 7, 6, ink)
    fill(img, 14, y + 10, 5, 4, belly)
    _legs(img, 14, y + 15, ink, pose["phase"], pose["tuck"])
    wag = -2 if pose["phase"] else 0
    fill(img, 7, y + 8 + wag, 6, 2, fur)
    put(img, 6, y + 7 + wag, ear)


def draw_dog(img, pal, pose) -> None:
    ink, fur, belly, ear, nose, tongue = pal
    y = 11 + pose["dy"]
    fill(img, 16, y - 1, 3, 4, ear)
    fill(img, 16, y + 2, 9, 7, ink)
    fill(img, 17, y + 3, 7, 5, fur)
    put(img, 21, y + 5, nose)
    fill(img, 22, y + 6, 3, 2, tongue)
    fill(img, 8, y + 5, 10, 6, ink)
    fill(img, 9, y + 6, 8, 4, fur)
    fill(img, 10, y + 8, 5, 2, belly)
    if pose["tuck"]:
        fill(img, 9, y + 11, 12, 2, ink)
    else:
        for index, x in enumerate((9, 12, 16, 19)):
            lift = 2 if (index % 2) == pose["phase"] else 0
            fill(img, x, y + 11 - lift, 2, 5, ink)
    wag = -3 if pose["phase"] else 0
    fill(img, 4, y + 4 + wag, 5, 2, fur)


def draw_dragon(img, pal, pose) -> None:
    ink, body, belly, wing, horn, eye = pal
    y = 11 + pose["dy"]
    flap = -4 if pose["jump"] or pose["phase"] else 0
    fill(img, 2, y + 4 + flap, 9, 4, wing)
    fill(img, 21, y + 4 + flap, 9, 4, wing)
    fill(img, 4, y + 2 + flap, 5, 2, horn)
    fill(img, 23, y + 2 + flap, 5, 2, horn)
    fill(img, 10, y + 4, 12, 6, ink)
    fill(img, 11, y + 5, 10, 4, body)
    fill(img, 12, y + 7, 6, 2, belly)
    fill(img, 18, y, 7, 5, ink)
    fill(img, 19, y + 1, 5, 3, body)
    put(img, 22, y + 2, eye)
    fill(img, 23, y - 2, 2, 2, horn)
    fill(img, 6, y + 6, 5, 2, body)
    put(img, 5, y + 5, horn)
    if not pose["tuck"]:
        fill(img, 12, y + 10, 2, 5, ink)
        fill(img, 16, y + 10, 2, 5, ink)
    else:
        fill(img, 11, y + 10, 8, 2, ink)


def draw_mini_drone(img, pal, pose) -> None:
    ink, body, panel, rotor, light, dark = pal
    y = 12 + pose["dy"]
    spin = pose["phase"] or pose["jump"]
    hubs = ((6, y), (22, y), (6, y + 12), (22, y + 12))
    for hx, hy in hubs:
        if spin:
            fill(img, hx - 2, hy + 1, 7, 1, rotor)
            fill(img, hx + 1, hy - 2, 1, 7, rotor)
        else:
            fill(img, hx, hy, 3, 3, rotor)
        put(img, hx + 1, hy + 1, dark)
    fill(img, 11, y + 4, 10, 2, ink)
    fill(img, 11, y + 10, 10, 2, ink)
    fill(img, 13, y + 5, 6, 6, ink)
    fill(img, 14, y + 6, 4, 4, body)
    fill(img, 15, y + 7, 2, 2, panel)
    put(img, 16, y + 6, light if spin else panel)


def draw_little_grok(img, pal, pose) -> None:
    """Small robot. Not a copy of any orchestrator sheet."""
    ink, body, face, antenna, eye, cheek = pal
    y = 8 + pose["dy"]
    bob = -1 if pose["phase"] or pose["jump"] else 0
    fill(img, 15, y + bob, 2, 3, antenna)
    put(img, 15, y - 1 + bob, antenna)
    fill(img, 11, y + 3, 10, 9, ink)
    fill(img, 12, y + 4, 8, 7, body)
    fill(img, 13, y + 6, 6, 3, face)
    fill(img, 14, y + 7, 4, 1, eye)
    put(img, 13, y + 8, cheek)
    put(img, 18, y + 8, cheek)
    fill(img, 13, y + 12, 6, 5, ink)
    fill(img, 14, y + 13, 4, 3, body)
    if pose["tuck"]:
        fill(img, 12, y + 17, 8, 2, ink)
    else:
        shift = 1 if pose["phase"] else 0
        fill(img, 13, y + 17 - shift, 2, 4, ink)
        fill(img, 17, y + 17 - (1 - shift), 2, 4, ink)


SKINS = (
    {
        "id": "imp",
        "label": "imp",
        "mode": "ground",
        "draw": draw_imp,
        "palette": (
            (42, 16, 32, 255),
            (210, 56, 72, 255),
            (242, 193, 78, 255),
            (255, 236, 220, 255),
            (90, 32, 64, 255),
            (255, 150, 130, 255),
        ),
    },
    {
        "id": "claude4",
        "label": "4-legged Claude",
        "mode": "ground",
        "draw": draw_claude4,
        "palette": (
            (44, 36, 22, 255),
            (196, 165, 116, 255),
            (240, 226, 196, 255),
            (138, 90, 50, 255),
            (26, 26, 26, 255),
            (232, 214, 170, 255),
        ),
    },
    {
        "id": "winged_light",
        "label": "winged light",
        "mode": "fly",
        "draw": draw_winged_light,
        "palette": (
            (58, 52, 40, 255),
            (255, 244, 200, 255),
            (255, 214, 120, 255),
            (255, 252, 236, 255),
            (214, 168, 64, 255),
            (255, 248, 180, 255),
        ),
    },
    {
        "id": "cat",
        "label": "cat",
        "mode": "ground",
        "draw": draw_cat,
        "palette": (
            (42, 33, 24, 255),
            (224, 122, 61, 255),
            (246, 210, 168, 255),
            (180, 78, 36, 255),
            (30, 107, 58, 255),
            (242, 163, 181, 255),
        ),
    },
    {
        "id": "dog",
        "label": "dog",
        "mode": "ground",
        "draw": draw_dog,
        "palette": (
            (36, 24, 16, 255),
            (141, 90, 50, 255),
            (230, 195, 154, 255),
            (92, 58, 34, 255),
            (26, 22, 20, 255),
            (224, 112, 112, 255),
        ),
    },
    {
        "id": "dragon",
        "label": "dragon",
        "mode": "fly",
        "draw": draw_dragon,
        "palette": (
            (20, 32, 24, 255),
            (58, 170, 106, 255),
            (216, 242, 196, 255),
            (30, 107, 68, 255),
            (230, 212, 138, 255),
            (242, 227, 107, 255),
        ),
    },
    {
        "id": "mini_drone",
        "label": "mini drone",
        "mode": "fly",
        "draw": draw_mini_drone,
        "palette": (
            (26, 32, 48, 255),
            (74, 163, 199, 255),
            (215, 238, 245, 255),
            (143, 208, 224, 255),
            (242, 227, 107, 255),
            (42, 58, 74, 255),
        ),
    },
    {
        "id": "little_grok",
        "label": "little Grok",
        "mode": "ground",
        "draw": draw_little_grok,
        "palette": (
            (28, 24, 48, 255),
            (107, 92, 255, 255),
            (232, 228, 255, 255),
            (255, 207, 74, 255),
            (20, 18, 31, 255),
            (154, 146, 255, 255),
        ),
    },
)


def build_sheet(spec: dict) -> Image.Image:
    sheet = Image.new("RGBA", (CELL * COLS, CELL * ROWS), (0, 0, 0, 0))
    ink = spec["palette"][0]
    for row in range(ROWS):
        for col in range(COLS):
            cell = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
            spec["draw"](cell, spec["palette"], pose_for(row, col))
            stamp_ph(cell, ink)
            sheet.paste(cell, (col * CELL, row * CELL), cell)
    allowed = {colour[:3] for colour in spec["palette"]}
    pixels = sheet.get_flattened_data() if hasattr(sheet, "get_flattened_data") else sheet.getdata()
    used = {pixel[:3] for pixel in pixels if pixel[3]}
    if len(spec["palette"]) > 6 or not used or not used <= allowed:
        raise RuntimeError(f"{spec['id']} palette is not within six colours")
    return sheet


def write_pack(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    skins = []
    for spec in SKINS:
        image = build_sheet(spec)
        filename = f"{spec['id']}.png"
        image.save(out_dir / filename)
        skins.append({
            "id": spec["id"],
            "label": spec["label"],
            "file": filename,
            "frame_w": CELL,
            "frame_h": CELL,
            "mode": spec["mode"],
            "placeholder": True,
        })
    manifest = {
        "frame": CELL,
        "note": "Code-generated placeholders. placeholder stays true until real sheets replace them.",
        "skins": skins,
    }
    text = json.dumps(manifest, indent=2) + "\n"
    (out_dir / "manifest.json").write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write placeholder subagent sheets.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    write_pack(args.out)
    print(f"wrote {len(SKINS)} placeholder sheets to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
