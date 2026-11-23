# Dungeon kit (placeholder)

**Source:** agents bot on the Agentic Server (Oscar).

**Date:** 23/11/2026

Static isometric building pieces for dungeon-style room dressing. See `INDEX.md` in this folder for per-sprite dimensions and anchor points.

Placeholder skin pending the owner's final OK before use in production builds.

## Origin and license

Every sprite here was drawn in code by our agents' scripts: a small JavaScript pixel engine sets each pixel (fills, outlines, dithering), a headless browser renders it, and the PNGs and the 4× copies are saved as they come out. The base pieces and objects (b01-b30, o01-o30) came first; the plaque, halos, badge, digits and avatar rows (b31-b37, `avatar-rows/`) were added with the same method (AG-2), and `manifest.json` is generated from these files and `INDEX.md`. No AI image generator and no third-party art or tilesets were used.

Private, all rights reserved.

## Avatar rows for `error` and `blocked`

`avatar-rows/error.png` and `avatar-rows/blocked.png` are 160×40 strips: 4 frames of 40×40, feet on the bottom row, transparent elsewhere. They are overlays, so they fit any skin: `error` adds a blinking warn sign, a cracked red floor and rising embers; `blocked` adds a chain round the feet, a swinging padlock and a draining hourglass. `avatar-rows/4x/` holds 4× copies.

To give a skin these rows, paste each overlay frame over the skin's own frame (bottom centre to bottom centre, no scaling) and append the results to the skin's sheet: `error` over the stand row (3) as row 5, `blocked` over the idle row (0) as row 6, matching the "Row 5+ — custom" convention in `sprite_loader.py`. Pointing `ANIM_ROW` at rows 5 and 6 is a separate change.

## manifest.json

`manifest.json` describes every 1× PNG in this folder and in `avatar-rows/`, as data only. Top level: `version`, `schema_version` (BLDG-SCHEMA, `1`), `tile` (iso tile width and height in px, `[32, 16]`) and `pieces`, keyed by file stem. Each piece has:

- `file`: path relative to this folder; `x4`: path of its 4× copy.
- `size`: `[w, h]` in px.
- `anchor`: `[x, y]` in px, the sprite pixel on the bottom centre (south vertex) of the footprint, as BLDG-SCHEMA asks: `INDEX.md` anchor `+ ((w - h) * 16, (w + h) * 8)`, light pieces `+ (0, 8)`. It can fall outside the image, e.g. rock below the tile or a torch beside its wall.
- `set`: on `o` pieces only, the object set from the `INDEX.md` group (`dungeon`, `skulls`, `spells`, `tables`, `torture`, `blood`, `barrels`, `potions`).
- `footprint`: `[cols, rows]` in grid cells; `[0, 0]` for wall-hung, light, mark and overlay pieces.
- `category`: one of `floor`, `wall`, `door`, `stair`, `light`, `state`, `decal`, `prop`, `ui`, `avatar-row`. `door` covers arches, doors and gates; `state` the node halos b32-b35; `ui` the plaque, badge and digits; `avatar-row` anchors frame 0 at its bottom centre (frames are 40×40).
- `light`: `true` when the piece shows a flame or glow (torches, halos, room lights, candles, crystal ball, magic circle, potions, brazier, cauldron).
