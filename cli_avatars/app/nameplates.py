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


def seat_inside(scene, settled, spots, inside, dragging, avoid=()) -> None:
    """Seat each inside nameplate above its sprite, kept on the floor.

    ROOM-ALIGN: a plate moves off the HUD boxes in ``avoid``; a standing avatar's also moves off the standing plates
    seated before it (front avatars first). Walkers do not push plates, so none jumps while one passes.
    """
    bounds = scene_bounds(scene)
    seated = []
    for index, aid in sorted(enumerate(settled), key=lambda row: _feet_y(row, spots, inside), reverse=True):
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
        still = av is not dragging and getattr(av, "_plate_at", None) == (int(x), int(y))
        av._plate_at = (int(x), int(y))
        if av is dragging:
            left, top = _pick([(left, top)], width, height, bounds, [])
        else:
            options = _options(left, top, width, height, int(y) + int(av.ah))
            left, top = _pick(options, width, height, bounds, [*avoid, *seated] if still else list(avoid))
        av._label_box = (left, top, width, height)
        if still:
            seated.append((left, top, left + width, top + height))


def _feet_y(row, spots, inside) -> float:
    index, aid = row
    av = inside.get(aid)
    center = spots.get(aid) if isinstance(spots, dict) else None
    if av is None or center is None:
        return float("-inf")
    return center[1] + av.ah / 2.0


def _options(left: int, top: int, width: int, height: int, feet: int) -> list[tuple[int, int]]:
    """Where a plate may go, nearest its head first: above, a row higher, under the feet, beside, higher still."""
    step = height + 2
    half = width // 2 + 2
    return [(left, top), (left, top - step), (left, feet + 2), (left - half, top), (left + half, top),
            (left, top - 2 * step), (left - half, top - step), (left + half, top - step), (left, top - 3 * step)]


def _pick(options, width: int, height: int, bounds, taken) -> tuple[int, int]:
    """The first option clear of ``taken`` boxes, else the one overlapping least; kept on the floor."""
    best = None
    for left, top in options:
        if bounds is not None:
            left = max(0, min(left, bounds[2] - width))
            top = max(0, min(top, bounds[3] - height))
        box = (left, top, left + width, top + height)
        hit = sum(_area(box, other) for other in taken)
        if hit == 0:
            return left, top
        if best is None or hit < best[0]:
            best = (hit, left, top)
    return best[1], best[2]


def _area(a, b) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0
