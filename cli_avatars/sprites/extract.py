"""Build built-in sprite sheets from source art in the sibling Images folder.

Pillow only. A missing source file prints a warning and skips that sheet.
"""

from pathlib import Path

from cli_avatars.paths import images_dir

try:
    from PIL import Image
except ImportError:
    Image = None


def _extract_bubble_sheet(path: Path) -> None:
    """
    Build bubble.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_Bubble.png.

    Source: ../Images/char_Bubble.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down):  walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up):    same sequence, back-facing
      Row 2 (right): same sequence, side-facing

    Target row → source (col, row) mapping:
      0 idle:  (1,0), (0,0), (1,0), (2,0)  — front neutral sway
      1 walk:  (0,2), (1,2), (2,2), (1,2)  — right walk cycle
      2 sit:   (3,0), (4,0), (3,0), (4,0)  — front type1/type2
      3 stand: (5,0), (6,0), (5,0), (6,0)  — front read1/read2
      4 jump:  (3,2), (1,2), (4,2), (2,2)  — right active frames
    """
    if Image is None:
        print("[sprites] Pillow required to extract bubble.png")
        return

    src_path = images_dir() / "char_Bubble.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping bubble.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    # (src_col, src_row) per target frame, row-major
    mapping = [
        # target row 0 — idle: front neutral sway
        [(1, 0), (0, 0), (1, 0), (2, 0)],
        # target row 1 — walk: right-facing walk cycle
        [(0, 2), (1, 2), (2, 2), (1, 2)],
        # target row 2 — sit/think: front type frames
        [(3, 0), (4, 0), (3, 0), (4, 0)],
        # target row 3 — stand/done: front read frames
        [(5, 0), (6, 0), (5, 0), (6, 0)],
        # target row 4 — jump/subagent: right active frames
        [(3, 2), (1, 2), (4, 2), (2, 2)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted bubble.png from char_Bubble.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_caine_sheet(path: Path) -> None:
    """
    Build caine.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_caine.png.

    Source: ../Images/char_caine.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down/front): walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up/back):    same sequence
      Row 2 (right/side): same sequence

    Target row → source (col, row) mapping:
      0 idle:  (1,0),(0,0),(1,0),(2,0)  — front neutral sway
      1 walk:  (0,2),(1,2),(2,2),(1,2)  — right-facing walk cycle
      2 sit:   (3,0),(4,0),(3,0),(4,0)  — front type1/type2 loop
      3 stand: (5,0),(6,0),(5,0),(6,0)  — front read1/read2 loop
      4 jump:  (3,2),(1,2),(4,2),(2,2)  — right active frames
    """
    if Image is None:
        print("[sprites] Pillow required to extract caine.png")
        return

    src_path = images_dir() / "char_caine.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping caine.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        [(1, 0), (0, 0), (1, 0), (2, 0)],   # idle — front neutral sway
        [(0, 2), (1, 2), (2, 2), (1, 2)],   # walk — right-facing cycle
        [(3, 0), (4, 0), (3, 0), (4, 0)],   # sit  — front type loop
        [(5, 0), (6, 0), (5, 0), (6, 0)],   # stand — front read loop
        [(3, 2), (1, 2), (4, 2), (2, 2)],   # jump — right active frames
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted caine.png from char_caine.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_amongo_sheet(path: Path) -> None:
    """
    Build amongo.png — 160×200 px, 40×40 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/Amongo Cat.png.

    Source: ../Images/Amongo Cat.png — 360×280 px, 9 cols × 7 rows, 40×40 cells.
      Row 0: idle  (cols 0–3 non-empty)
      Row 1: walk  (cols 0–3 non-empty)
      Row 2: sit   (col 0 only)
      Row 3: stand (col 0 only)
      Row 4: jump  (col 0 only)
      Row 5: sleep (col 0 only)
      Row 6: spawn/despawn effect — skipped

    Target row → source (col, row) mapping:
      0 idle:  (0,0),(1,0),(2,0),(3,0)  — full 4-frame idle cycle
      1 walk:  (0,1),(1,1),(2,1),(3,1)  — full 4-frame walk cycle
      2 sit:   (0,2)                    — single sit frame, rest transparent
      3 stand: (0,3),(0,0)              — stand + idle alternating
      4 jump:  (0,4),(1,1),(0,4),(3,1)  — jump alternating with walk for bounce
    """
    if Image is None:
        print("[sprites] Pillow required to extract amongo.png")
        return

    src_path = images_dir() / "Amongo Cat.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping amongo.png")
        return

    FW, FH = 40, 40
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        # target row 0 — idle: full 4-frame cycle
        [(0, 0), (1, 0), (2, 0), (3, 0)],
        # target row 1 — walk: full 4-frame cycle
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        # target row 2 — sit/think: single sit frame (loader loops it)
        [(0, 2)],
        # target row 3 — stand/done: stand + idle alternating
        [(0, 3), (0, 0)],
        # target row 4 — jump/subagent: jump frame alternating with walk for bounce
        [(0, 4), (1, 1), (0, 4), (3, 1)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted amongo.png from Amongo Cat.png ({out.width}x{out.height} px, 40x40 cells)")
