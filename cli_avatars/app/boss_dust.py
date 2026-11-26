"""BOSS-ROOM.1: when the Oni Pit or the Crypt grows or shrinks, its walls slide a tile a step (``boss_rooms.Grow``)
and throw up stone dust along every edge that moved, with a stone grind (held while a task is in focus; quiet while
a boss cue plays or waits, so a hit or a roar is never buried under it).

``boss_view`` calls ``update`` with the floor plan and ``paint`` each frame. Puffs live ``PUFF_S`` and drift up; at
most ``MAX_PUFFS`` at once. Canvas items are pooled and changed in place.
"""

from __future__ import annotations

import sys

import focus
from cli_avatars.app import boss_room_art as art
from cli_avatars.app import boss_rooms, cues

TAG = "boss-dust"
PUFF_S = 0.7
MAX_PUFFS = 64
GRIND_GAP_S = 1.2


def dust_for(book) -> "Dust":
    found = getattr(book, "_boss_dust", None)
    if found is None:
        found = book._boss_dust = Dust(book.app, book)
    return found


def moved(before: tuple[int, int, int, int], after: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    """Floor points along each edge of ``after`` that is not where it was in ``before``, one per tile."""
    u0, v0, w, h = after
    b0, c0, bw, bh = before
    out: list[tuple[float, float]] = []
    if u0 != b0:
        out += [(u0 + 0.5, v0 + k + 0.5) for k in range(h)]
    if u0 + w != b0 + bw:
        out += [(u0 + w, v0 + k + 0.5) for k in range(h)]
    if v0 != c0:
        out += [(u0 + k + 0.5, v0 + 0.5) for k in range(w)]
    if v0 + h != c0 + bh:
        out += [(u0 + k + 0.5, v0 + h) for k in range(w)]
    return out


class Dust:
    def __init__(self, app, book=None) -> None:
        self.app, self.book = app, book
        self.rooms: dict[str, tuple[int, int, int, int]] = {}
        self.puffs: list[tuple[float, float, float]] = []
        self.played: list[str] = []
        self.held: str | None = None
        self._grind = float("-inf")
        self._items: list[int] = []
        self._photos: dict[tuple, object] = {}

    def _directory(self):
        found = getattr(self.app, "_chat_directory", None)
        return found() if callable(found) else None

    def update(self, plan, now: float) -> None:
        stirred = False
        for name in (boss_rooms.PIT, boss_rooms.CRYPT):
            floor = plan.floor(name) if plan is not None else None
            if floor is None:
                self.rooms.pop(name, None)
                continue
            rect = (floor.u0, floor.v0, floor.w, floor.h)
            before = self.rooms.get(name)
            self.rooms[name] = rect
            if before is not None and before != rect:
                self.puffs += [(u, v, now) for u, v in moved(before, rect)]
                stirred = True
        self.puffs = [p for p in self.puffs if now - p[2] < PUFF_S][-MAX_PUFFS:]
        root = self._directory()
        busy = root is not None and focus.current(root) is not None
        boss = getattr(self.book, "_boss", None)
        quiet = boss is not None and (boss.held is not None or now - boss.cued < GRIND_GAP_S)
        if stirred and now - self._grind >= GRIND_GAP_S and not quiet:
            self._grind = now
            if busy:
                self.held = "grind"
            else:
                cues.play(self.app, "grind")
                self.played.append("grind")
        if self.held and not busy:
            name, self.held = self.held, None
            cues.play(self.app, name)
            self.played.append(name)

    def paint(self, scene, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None or painter.to_canvas(0, 0) is None:
            self.puffs = []
        s = max(1, int(getattr(painter, "_scale", 1) or 1))
        while len(self._items) > len(self.puffs):
            scene.delete(self._items.pop())
        for n, (u, v, born) in enumerate(self.puffs):
            t = min(1.0, max(0.0, (now - born) / PUFF_S))
            frame = min(art.PUFF_FRAMES - 1, int(t * art.PUFF_FRAMES))
            x, y = painter.to_canvas(u, v)
            at = (round(x + ((n * 7) % 5 - 2) * s), round(y - (4 + 10 * t) * s))
            photo = self._photo(scene, frame, s)
            if n < len(self._items) and scene.find_withtag(self._items[n]):
                scene.itemconfigure(self._items[n], image=photo)
                scene.coords(self._items[n], *at)
            elif n < len(self._items):
                self._items[n] = scene.create_image(*at, image=photo, anchor="s", tags=(TAG,))
            else:
                self._items.append(scene.create_image(*at, image=photo, anchor="s", tags=(TAG,)))
        if self._items:
            scene.tag_raise(TAG)

    def _photo(self, scene, frame: int, s: int):
        key = (frame, s)
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            image = art.puff(frame)
            image = image.resize((image.width * s, image.height * s), Image.NEAREST) if s > 1 else image
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
        return found
