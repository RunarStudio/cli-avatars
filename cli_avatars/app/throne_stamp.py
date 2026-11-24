"""START.1: the main session's room gets the throne room's code-drawn dais, throne and carpet. No Tk.

The pieces come from ``throne_pieces`` on the same 16x8 iso grid as the kit, so they are pasted
into the composed rooms image at the room's own tiles, as the Throne tab places them.
"""

from __future__ import annotations

import numpy as np

TILE_HALF_W, TILE_HALF_H = 16, 8

# piece, (u, v, z) inside the room's floor, as the Throne tab's hall puts them
PLACES = (("carpet", (4.5, 3.5, 0.0)), ("dais", (0.3, 1.9, 0.0)), ("throne", (0.45, 3.4, 0.75)))
_SPRITES: dict[str, object] = {}


def _sprite(name: str):
    if name not in _SPRITES:
        from cli_avatars.app.throne_pieces import capture, carpet, dais, throne

        _SPRITES[name] = capture({"carpet": carpet, "dais": dais, "throne": throne}[name])
    return _SPRITES[name]


def stamp_thrones(image, layout: dict | None) -> int:
    """Paste the pieces into every throne room of ``layout``; the count of rooms stamped."""
    from PIL import Image

    left, top = image.info.get("origin", (0, 0))
    done = 0
    for room in (layout or {}).get("rooms") or []:
        origin = room.get("origin") if isinstance(room, dict) else None
        if not room or not room.get("throne") or not isinstance(origin, list) or len(origin) != 2:
            continue
        for name, (u, v, z) in PLACES:
            s = _sprite(name)
            uu, vv = origin[0] + 1 + u, origin[1] + 1 + v
            x = round((uu - vv) * TILE_HALF_W) - left - s.ax
            y = round((uu + vv) * TILE_HALF_H - z * TILE_HALF_W) - top - s.ay
            piece = Image.fromarray(np.clip(s.data, 0, 255).astype(np.uint8), "RGBA")
            layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            layer.paste(piece, (x, y))
            image.alpha_composite(layer)
        done += 1
    return done
