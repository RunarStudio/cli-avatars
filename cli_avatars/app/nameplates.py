"""Nameplate boxes for the Dungeon floor.

The sprite draws whatever box this seats. Overlapping plates slide sideways
before the paint, so Mira and Orch stay readable when the ring stacks them.
"""

from __future__ import annotations


def plate_pixels(scene, text: str) -> tuple[int, int]:
    """Measured nameplate size. Courier 7 bold, the same face the sprite draws."""
    import tkinter.font as tkfont

    font = getattr(scene, "_plate_font", None)
    if font is None:
        font = tkfont.Font(scene, family="Courier", size=7, weight="bold")
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
    """Seat each inside nameplate, then separate any that still overlap."""
    from activity import Plate, nudge_plates, plate_box

    plates = []
    owners = []
    sprites = []
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
        sprites.append((int(x), int(y), int(av.aw), int(av.ah)))
        try:
            text = av.plate_text()
            width, height = plate_pixels(scene, text)
        except Exception:
            av._label_box = None
            continue
        left, top, width, height = plate_box(x, y, av.aw, width, height)
        plate = Plate()
        plate.agent_id = getattr(getattr(av, "agent", None), "agent_id", "")
        plate.x, plate.y, plate.w, plate.h = left, top, width, height
        plates.append(plate)
        owners.append(av)
    nudge_plates(plates, scene_bounds(scene), occupied=sprites)
    for av, plate in zip(owners, plates, strict=True):
        av._label_box = plate.box()
