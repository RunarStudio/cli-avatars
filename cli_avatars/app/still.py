"""NOFLICKER: Dungeon canvas writes that skip a no-op, so an idle frame repaints nothing.

Tk repaints an item's area on every ``coords``, option or stacking write, even when nothing changes. ``LAYERS`` is
the floor's top stacking, lowest first, as the frame raises it (crypt in ``draw_inside``, time-lapse entry, map
control, then the boss after idle).
"""

from __future__ import annotations

LAYERS = ("crypt", "crypt-skull", "crypt-label", "lapse-entry", "nav", "boss", "boss-list")


def move(canvas, item, *xy) -> None:
    """``canvas.coords(item, *xy)`` unless the item is already there."""
    if [round(float(v), 1) for v in canvas.coords(item) or ()] != [round(float(v), 1) for v in xy]:
        canvas.coords(item, *xy)


def lift(canvas, tag: str) -> None:
    """``canvas.tag_raise(tag)`` unless only its own items or later ``LAYERS`` (all, for another tag) lie above it."""
    mine = canvas.find_withtag(tag)
    if not mine:
        return
    order = tuple(canvas.find_all() or ())
    if not set(mine) <= set(order):
        canvas.tag_raise(tag)
        return
    low = min(order.index(item) for item in mine)
    later = LAYERS[LAYERS.index(tag) + 1:] if tag in LAYERS else LAYERS
    allowed = set(mine).union(*(canvas.find_withtag(t) for t in later))
    if any(item not in allowed for item in order[low:]):
        canvas.tag_raise(tag)


def sink(canvas, tag: str) -> None:
    """``canvas.tag_lower(tag)`` unless its items are already the lowest."""
    mine = canvas.find_withtag(tag)
    if mine and set(tuple(canvas.find_all() or ())[:len(mine)]) != set(mine):
        canvas.tag_lower(tag)


class Pool:
    """Images under one tag reused frame to frame: ``begin``, ``image`` per mark, ``end`` drops the rest."""

    def __init__(self, canvas, tag: str) -> None:
        self.canvas, self.tag = canvas, tag
        self.items: list[int] = []
        self.used = 0

    def begin(self) -> None:
        self.used = 0

    def image(self, x: float, y: float, photo) -> None:
        canvas, at = self.canvas, self.used
        if at < len(self.items) and canvas.type(self.items[at]):
            move(canvas, self.items[at], x, y)
            if str(canvas.itemcget(self.items[at], "image")) != str(photo):
                canvas.itemconfigure(self.items[at], image=photo)
        else:
            self.items[at:at + 1] = [canvas.create_image(x, y, image=photo, anchor="nw", tags=(self.tag,))]
        self.used += 1

    def end(self) -> None:
        for item in self.items[self.used:]:
            self.canvas.delete(item)
        del self.items[self.used:]


def pool(canvas, tag: str) -> Pool:
    """The canvas's one ``Pool`` for ``tag``."""
    pools = canvas.__dict__.setdefault("_still_pools", {})
    if tag not in pools:
        pools[tag] = Pool(canvas, tag)
    return pools[tag]
