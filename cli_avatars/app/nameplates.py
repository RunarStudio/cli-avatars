"""Nameplate boxes for the Dungeon floor.

The sprite draws whatever box this seats. A plate keeps one offset above its
sprite, so it follows a walking avatar and never jumps when a neighbour passes.
"""

from __future__ import annotations

import text_fonts as fonts


def plate_pixels(scene, text: str) -> tuple[int, int]:
    """Measured nameplate size. The 7 pt bold text face, the same one the sprite draws."""

    font = getattr(scene, "_plate_font", None)
    if font is None:
        font = fonts.tk_font(scene, 7, "bold")
        try:
            scene._plate_font = font
        except Exception:
            pass
    lines = text.split("\n") or [""]
    width = max(int(font.measure(line or " ")) for line in lines)
    height = int(font.metrics("linespace")) * len(lines)
    # measure is a little short of the bold ink create_text draws.
    return max(1, width + 6), max(1, height + 2)


def scene_bounds(scene) -> tuple[int, int, int, int] | None:
    try:
        width = int(scene.winfo_width())
        height = int(scene.winfo_height())
    except Exception:
        return None
    if width < 2 or height < 2:
        return None
    return (0, 0, width, height)


def seat_inside(scene, settled, spots, inside, dragging) -> None:
    """Seat each inside nameplate above its sprite, kept on the floor."""
    bounds = scene_bounds(scene)
    for index, aid in enumerate(settled):
        av = inside.get(aid)
        if av is None:
            continue
        if av is dragging:
            x, y = av.x, av.y
        else:
            center = spots.get(aid) if isinstance(spots, dict) else spots[index]
            if center is None:
                center = (0.0, 0.0)
            x = center[0] - av.aw / 2.0
            y = center[1] - av.ah / 2.0
        try:
            text = av.plate_text()
            width, height = plate_pixels(scene, text)
        except Exception:
            av._label_box = None
            continue
        # The sprite paints at int(x), int(y): anchor there too, or the offset flips by a pixel.
        left = int(x) + int(av.aw) // 2 - width // 2
        top = int(y) - 4 - height
        if bounds is not None:
            left = max(0, min(left, bounds[2] - width))
            top = max(0, min(top, bounds[3] - height))
        av._label_box = (left, top, width, height)
