"""SKIN on the phone map: a picked sheet's idle and walk rows at native pixels, keyed ``name`` or ``name-<hue>``."""

from __future__ import annotations

import io
import re
import threading

_KEY = re.compile(r"^([a-z_]{1,24})(?:-(\d{1,3}))?$")
_CACHE: dict[str, tuple[bytes, int, int, int]] = {}
_LOCK = threading.Lock()


def key_of(skin: str) -> str:
    """Sprite key of a picked skin: ``caine_h90`` is ``caine-90``."""
    base, sep, tail = skin.rpartition("_h")
    return f"{base}-{tail}" if sep and tail.isdigit() and base else skin


def sheet_png(key: str) -> tuple[bytes, int, int, int] | None:
    """``(png strip, frame w, frame h, frames)``: idle on row 0, walk on row 1, hue turned as the desktop does."""
    from cli_avatars.tuning import TUNING
    from rooms import _SHEETS

    found = _KEY.match(key)
    if found is None or found.group(1) not in _SHEETS or (found.group(2) and int(found.group(2)) > 359):
        return None
    cache_key = f"{key}/{TUNING.anim_mode}"
    with _LOCK:
        if cache_key in _CACHE:
            return _CACHE[cache_key]
    from PIL import Image

    from sprite_loader import hue_rotate_image

    filename, fw, fh = _SHEETS[found.group(1)]
    try:
        with Image.open(_sheet_file(filename)) as img:
            sheet = img.convert("RGBA")
    except (OSError, ValueError):
        return None
    if found.group(2):
        sheet = hue_rotate_image(sheet, float(found.group(2)))
    rows = []
    for row in (0, 1):
        cells = []
        for col in range(sheet.width // fw):
            cell = sheet.crop((col * fw, row * fh, col * fw + fw, row * fh + fh))
            if cell.getchannel("A").getbbox() is None:
                break
            cells.append(cell)
        rows.append(cells if cells or not rows else rows[0])
    if not rows[0]:
        return None
    frames = max(len(r) for r in rows)
    strip = Image.new("RGBA", (fw * frames, fh * 2), (0, 0, 0, 0))
    for y, cells in enumerate(rows):
        for i in range(frames):
            strip.paste(cells[i % len(cells)], (i * fw, y * fh))
    out = io.BytesIO()
    strip.save(out, "PNG")
    result = (out.getvalue(), fw, fh, frames)
    with _LOCK:
        _CACHE[cache_key] = result
    return result


def clear() -> None:
    with _LOCK:
        _CACHE.clear()


def _sheet_file(filename: str):
    """SMOOTHANIM: the smoothed sheet when Smooth is on, as the desktop loads it."""
    from bundle_paths import asset_path
    from cli_avatars.tuning import TUNING

    smooth = asset_path("Sprites", "smooth", filename)
    return smooth if TUNING.anim_mode == "smooth" and smooth.is_file() else asset_path("Sprites", filename)


def timing(key: str) -> dict:
    """``{"ms": [idle, walk]}`` per frame for a picked sheet under Smooth; the page keeps its own pace otherwise."""
    from cli_avatars.tuning import TUNING
    from rooms import _SHEETS

    found = _KEY.match(key)
    if TUNING.anim_mode != "smooth" or found is None or found.group(1) not in _SHEETS:
        return {}
    return {"ms": [round(TUNING.anim_ms["idle"]), round(TUNING.anim_ms["busy"])]}
