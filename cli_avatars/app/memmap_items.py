"""Canvas items that remember what they were last given (MEMMAP.4).

Every coords / itemconfigure is a Tcl call, and on Windows each costs about
seven times what it does on Linux. ``Items`` only sends what changed, so a
redraw with unchanged data makes no calls at all.
"""

from __future__ import annotations


class Items:
    def __init__(self, canvas):
        self.canvas = canvas
        self._options: dict[int, tuple] = {}
        self._coords: dict[int, tuple] = {}
        self.restack = False

    def create(self, kind: str, xy: tuple, fixed: dict, **options) -> int:
        """New item; ``options`` are what later ``config`` calls compare against, ``fixed`` never changes."""
        item = getattr(self.canvas, "create_" + kind)(*xy, **fixed, **options)
        self._coords[item] = xy
        self._options[item] = tuple(sorted(options.items()))
        self.restack = True
        return item

    def config(self, item: int, **options) -> None:
        key = tuple(sorted(options.items()))
        if self._options.get(item) != key:
            self.canvas.itemconfigure(item, **options)
            self._options[item] = key

    def place(self, item: int, xy: tuple) -> None:
        if self._coords.get(item) != xy:
            self.canvas.coords(item, *xy)
            self._coords[item] = xy

    def update(self, item: int | None, kind: str, xy: tuple, fixed: dict, **options) -> int:
        """``item`` moved and restyled, or a new one when ``item`` is None."""
        if item is None:
            return self.create(kind, xy, fixed, **options)
        self.place(item, xy)
        self.config(item, **options)
        return item

    def delete(self, *items: int) -> None:
        for item in items:
            self._options.pop(item, None)
            self._coords.pop(item, None)
        self.canvas.delete(*items)
