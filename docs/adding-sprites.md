# Adding Custom Sprite Sheets

CLI Avatars uses the **Stream Avatars row convention** — the same format used by the popular Twitch streaming app. Any sprite sheet in this format works out of the box.

---

## Sprite Sheet Format

Each row of the sheet is one animation. Each column in that row is one frame.

```
┌──────┬──────┬──────┬──────┐  ← Row 0: IDLE
│ fr 0 │ fr 1 │ fr 2 │      │    (trailing blank cells are auto-skipped)
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 1: RUN / WALK
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │      │      │  ← Row 2: SIT
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │      │  ← Row 3: STAND
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 4: JUMP
└──────┴──────┴──────┴──────┘
```

| Row | Animation name | When the overlay uses it |
|-----|---------------|--------------------------|
| 0 | idle | Agent is waiting between turns |
| 1 | run / walk | Agent is using a tool (busy) |
| 2 | sit | Agent is thinking / generating a response |
| 3 | stand | Turn complete / error |
| 4 | jump | Sub-agent is active |
| 5+ | custom | Not currently mapped — safe to include |

### Requirements

- **Format:** PNG with transparency (RGBA). JPEG is not supported (no alpha channel).
- **Cell size:** All cells must be the same width and height. Common sizes: 32×32, 40×40, 48×48, 60×60.
- **Cell height:** Can differ from width — e.g. `meowatar` uses 60 wide × 50 tall cells.
- **Background:** Must be transparent. Solid white/colored backgrounds will render as a colored box on screen.

---

## Adding a Sheet in 3 Steps

### Step 1 — Place the PNG in `Sprites/`

```
cli-avatars/
└── Sprites/
    └── MyCharacter.png   ← put it here
```

### Step 2 — Register it in `overlay.py`

Open `overlay.py` and find the `_load_sprites()` method. Add one line to the `sheets` list:

```python
sheets = [
    ("meowatar",  "meowatar.png",  60, 50),
    ("michimaru", "Michimaru.png", 40, 51),
    ("ponmi",     "ponmi.png",     48, 48),
    ("mychar",    "MyCharacter.png", 48, 48),   # ← add this
]
```

The four values are: `(name, filename, frame_width, frame_height)`.

- `name` — the identifier used in the skin picker. Use lowercase, no spaces.
- `filename` — exact filename inside `Sprites/`, including capitalisation.
- `frame_width` — width of one cell in pixels (before scaling).
- `frame_height` — height of one cell in pixels. Set to the same as `frame_width` if cells are square.

### Step 3 — Restart

```bash
python overlay.py
```

Open the skin picker (right-click → **Skins**). Your skin appears in the list.

---

## Inspecting a Sheet

Not sure of the cell size? Use the built-in info command:

```bash
python sprite_loader.py info Sprites/MyCharacter.png 48 48
```

Output:

```
SpriteSheet 'MyCharacter.png'
  Image   : 192x240 px
  Cell    : 48x48 px  (scale=1.0x)
  Grid    : 4 cols x 5 rows
  Animations:
    row 0  [idle    ]  2 frame(s)
    row 1  [run     ]  4 frame(s)
    row 2  [sit     ]  2 frame(s)
    row 3  [stand   ]  3 frame(s)
    row 4  [jump    ]  3 frame(s)
```

Try different cell sizes if the layout looks wrong (the frame count per row should match your sheet's design).

---

## Converting from JPEG

If you only have a JPEG source, convert it first — but note that you will still need to manually remove the background in an image editor (GIMP, Aseprite, Photoshop) since JPEG has no transparency:

```bash
python sprite_loader.py convert source.jpg Sprites/MyCharacter.png
```

This creates a PNG with all pixels fully opaque (alpha = 255). Open the PNG in an editor and remove the background before using it.

---

## Hue Shifting

The skin picker includes a **hue slider** that rotates all colors of the sprite sheet without modifying the file. This means one sprite sheet can produce many color variants — assign different hues to different agents.

Hue shifting requires `numpy`:

```bash
pip install numpy
```

Without numpy, the overlay still runs but hue shifting is skipped.

---

## Creating Sheets from Scratch

Recommended tools:
- **[Aseprite](https://www.aseprite.org/)** — dedicated pixel art + animation tool. Export sprite sheets directly. Set canvas to your cell size (e.g. 48×48), animate each row, then File → Export Sprite Sheet with horizontal strip layout.
- **GIMP** — free alternative. Use Filters → Animation for frames.
- **Libresprite** — free fork of an older Aseprite version.

The minimum viable sheet is just Row 0 (idle) with 1–2 frames. All other rows are optional — the overlay falls back to the first row that has frames if a row is missing.

---

## Subagent skins

Subagent sheets live in `Sprites/subagents/` and are listed in `manifest.json` beside them. Each entry has its own `frame_w` and `frame_h` (the placeholders are 32×32), a `mode` of `fly` or `ground`, and the png file name. The overlay loads that size per skin.

These sheets are not the orchestrator Stream Avatars grid. `manifest.json` lists three rows:

| Row | Name | Frames | When it plays |
|-----|------|--------|----------------|
| 0 | idle | 4 | the child is waiting |
| 1 | working | 4 | the subagent is busy or thinking |
| 2 | dying | 4 | the subchat or task closes, or the parent avatar goes away |

Dying plays once, about 4 frames at 120 ms. The spring line shrinks toward the child during that pass. The child stays where it is: the leash is ignored, and dragging the parent does not pull it. When the row finishes, the avatar is removed. A missing row falls back to the first row that has frames.

`fly` hovers above the orchestrator's head. `ground` hangs below it on the same spring. Dropping a finished sheet in place of a placeholder means setting `placeholder` to false and keeping the id, so existing `config.json` assignments still resolve. Keep the idle, working, and dying rows.

Regenerate the stand-ins with `python tools/gen_subskin_placeholders.py`. Those files are code, not the final art.

## Smooth animation

Settings, Display: **Animation** is Smooth (the default) or Classic, saved as `animation` in `config.json`. Smooth loads `Sprites/smooth/<sheet>.png`; Classic loads the original sheet with the old frame ticks. The phone view draws the same frames.

The smooth sheets are generated in code from the originals, which are only read:

```bash
python tools/gen_smooth_sprites.py
```

Run it again after any change to a sheet in `Sprites/`, then `python -m unittest tests.test_smooth_anim`. Each row keeps its keys on the even frames and gets an in-between on each odd one: every changed part moves half its way on whole pixels, the part above the waist leads and the part below follows (1 px of squash or stretch), and a part that changes shape holds its key. A row with fewer than 4 keys also breathes (1 px stretch and squash above the waist, feet fixed), so every row has at least 8 frames. No blur and no alpha crossfade: every pixel is a colour of that sheet. Per-character tuning (waist line, reach, rigid share) is `TUNES` in `cli_avatars/sprites/smooth.py`.

Timing is in `cli_avatars/tuning.py`: `anim_ms` per state (idle breathes slow), `anim_ease` (keys hold longer, in-betweens pass quicker), `walk_stride` (sprite px per walk cycle; the desktop walk advances by the distance walked so the feet do not slide) and `walk_ease` (a Dungeon walk eases in and out). Rows with fewer than 8 frames, such as the subagent sheets, keep the Classic ticks.
