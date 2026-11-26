"""SMOOTHANIM: write Sprites/smooth/<sheet>.png from each character sheet. Re-runnable; the originals are only read.

    python tools/gen_smooth_sprites.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from cli_avatars.sprites.smooth import TUNES, palette, smooth_sheet  # noqa: E402

SPRITES = ROOT / "Sprites"


def main() -> int:
    from cli_avatars.sprites.registry import SHEETS

    out_dir = SPRITES / "smooth"
    out_dir.mkdir(exist_ok=True)
    for name, fname, fw, fh in SHEETS:
        src = SPRITES / fname
        if not src.exists():
            print(f"skip {name}: no {fname}")
            continue
        with Image.open(src) as image:
            made = smooth_sheet(image, fw, fh, TUNES[name])
            if not palette(made) <= palette(image):
                print(f"{name}: a colour outside the sheet's palette")
                return 1
        made.save(out_dir / fname, optimize=True)
        print(f"{name}: {made.width // fw} frames max -> {(out_dir / fname).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
