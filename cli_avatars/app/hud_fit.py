"""ROOM-ALIGN: the room HUD (door sign with its tier chip, counts plaque) stays inside the Dungeon view.

A room's sign and plaque move together, so the pair never splits; a pair with its middle on screen is pulled fully
inside. Nameplates go under the HUD and are seated clear of it (``nameplates.seat_inside``).
"""

from __future__ import annotations

from cli_avatars.app.nameplates import scene_bounds, seat_inside

SIGN, PLAQUE = "door-sign", "door-plaque"


def groups(book) -> list[list[int]]:
    """Canvas items of each room's HUD: its sign and its plaque."""
    found: dict[str, list[int]] = {}
    for holder in (getattr(book, "_door_signs", None), getattr(book, "_door_plaques", None)):
        for name, item in (getattr(holder, "_items", None) or {}).items():
            found.setdefault(name, []).append(item)
    return list(found.values())


def shift(box, bounds) -> tuple[int, int]:
    """Move that brings ``box`` inside ``bounds``; none when its middle is off the view or it cannot fit."""
    left, top, right, bottom = box
    cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
    if not (bounds[0] <= cx <= bounds[2] and bounds[1] <= cy <= bounds[3]):
        return (0, 0)
    dx = max(0, bounds[0] - left) - max(0, right - bounds[2]) if right - left <= bounds[2] - bounds[0] else 0
    dy = max(0, bounds[1] - top) - max(0, bottom - bounds[3]) if bottom - top <= bounds[3] - bounds[1] else 0
    return (int(dx), int(dy))


def keep_in_view(book, scene) -> list[tuple[int, int, int, int]]:
    """Pull each HUD pair inside the view; the HUD boxes after the move."""
    bounds = scene_bounds(scene)
    out = []
    for items in groups(book):
        boxes = [b for b in (scene.bbox(i) for i in items) if b]
        if not boxes:
            continue
        union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        dx, dy = shift(union, bounds) if bounds is not None else (0, 0)
        if dx or dy:
            for item in items:
                scene.move(item, dx, dy)
        out += [(b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy) for b in boxes]
    return out


def labels_under(scene, inside: dict) -> None:
    """Nameplate text goes just under the lowest HUD item, so a label never covers a sign or a plaque."""
    hud = scene.find_withtag(f"{SIGN}||{PLAQUE}")
    if not hud:
        return
    for av in inside.values():
        label = getattr(av, "lbl_id", None)
        if label is not None:
            scene.tag_lower(label, hud[0])


def seat(book, scene, settled, spots, dragging) -> None:
    """This frame's nameplates, seated clear of the HUD once it is pulled inside the view."""
    seat_inside(scene, settled, spots, book.app._inside, dragging, keep_in_view(book, scene))
