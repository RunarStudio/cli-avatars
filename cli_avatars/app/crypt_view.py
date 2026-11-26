"""BOSS-ROOM.1 on the Dungeon floor: the Crypt's skulls, one per forgotten card (docs/backlog-boss.md).

``boss_view`` calls ``update`` and ``paint`` each frame. The skulls come from ``boss_rooms.read`` (the boss view's
own read refreshes it). Each skull keeps its niche (``boss_rooms.slots``): niches line the back walls, two rows a
tile, lower row first; skulls past the niches pile on the floor. A new skull drops into its niche with a small
rattle (held while a task is in focus). A carved plaque counts them. Hover a skull for its card's title and how long
it has been forgotten; click it to open the card. Canvas items are made once and moved in place.
"""

from __future__ import annotations

import logging
import sys

import focus
from cli_avatars.app import boss_room_art as art
from cli_avatars.app import boss_rooms, cues

TAG = "crypt"
DROP_S = 0.5
DROP_PX = 46
_log = logging.getLogger("cli_avatars.crypt")


def view_for(book) -> "CryptView":
    found = getattr(book, "_crypt", None)
    if found is None:
        found = book._crypt = CryptView(book)
    return found


class CryptView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.rows: list[dict] = []
        self.slots: dict[str, int] = {}
        self.born: dict[str, float] = {}
        self.played: list[str] = []
        self.held: str | None = None
        self.hot: str | None = None
        self._seen: set[str] | None = None
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._label: list[int] = []
        self._label_key: tuple | None = None

    def _directory(self):
        found = getattr(self.app, "_chat_directory", None)
        return found() if callable(found) else None

    def update(self, now: float) -> None:
        root = self._directory()
        if root is None:
            return
        self.rows = boss_rooms.read(root, now)[1]
        ids = [r["id"] for r in self.rows]
        self.slots = boss_rooms.slots(self.slots, ids)
        fresh = [i for i in ids if self._seen is not None and i not in self._seen]
        self._seen = set(ids)
        for i in fresh:
            self.born[i] = now
        self.born = {i: t for i, t in self.born.items() if i in self._seen and now - t < DROP_S}
        if fresh:
            self._cue("rattle", fresh)
        if self.held and focus.current(root) is None:
            name, self.held = self.held, None
            cues.play(self.app, name)
            self.played.append(name)

    def _cue(self, name: str, cards: list[str]) -> None:
        root = self._directory()
        try:
            task = focus.current(root) if root is not None else None
        except Exception:
            task = None
        if task is not None and task not in cards:
            self.held = name
            return
        cues.play(self.app, name)
        self.played.append(name)

    def open_card(self, card: str) -> None:
        view = getattr(self.app, "dungeon", None)
        panel = getattr(self.app, "_tasks_panel", None)
        if view is not None:
            view.show_center("tasks")
            if panel is not None:
                panel.open_card(card)

    # --- drawing ---------------------------------------------------------------------------------------
    def paint(self, scene, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        room = boss_rooms.room(getattr(painter, "layout", None), boss_rooms.CRYPT_KIND)
        if tk is None or not isinstance(scene, tk.Canvas) or room is None or painter.to_canvas(0, 0) is None:
            self._drop(scene, set())
            self._paint_label(scene, None, (0, 0))
            return
        s = max(1, int(painter._scale))
        keep: set[str] = set()
        spots = boss_rooms.niches(room)
        for n, (u, v, side, lift) in enumerate(spots):
            x, y = painter.to_canvas(u, v)
            keep.add(f"n{n}")
            self._image(scene, f"n{n}", ("niche", side, s), (x, y - lift * s), "s", None)
        by_slot = {self.slots[r["id"]]: r for r in self.rows if r["id"] in self.slots}
        piled = sorted(slot for slot in by_slot if slot >= len(spots))
        floor = boss_rooms.heap(room, len(piled))
        for slot, row in sorted(by_slot.items()):
            if slot < len(spots):
                u, v, _side, lift = spots[slot]
            elif piled.index(slot) < len(floor):
                u, v, lift = floor[piled.index(slot)]
            else:
                continue
            x, y = painter.to_canvas(u, v)
            y -= (lift + 1) * s
            born = self.born.get(row["id"])
            if born is not None:
                t = min(1.0, max(0.0, (now - born) / DROP_S))
                y -= round(DROP_PX * s * (1 - t) ** 2)
            name = f"s:{row['id']}"
            keep.add(name)
            self._image(scene, name, ("skull", self.hot == row["id"], s), (x, y), "s", row["id"])
        if self.rows:
            (u0, v0), (w, h) = room["origin"], room["size"]
            keep.add("plaque")
            self._image(scene, "plaque", ("plaque", len(self.rows), s), painter.to_canvas(u0 + w - 0.6, v0 + h / 2.0),
                        "center", None)
        self._drop(scene, keep)
        hot = next((r for r in self.rows if r["id"] == self.hot), None)
        at = self._at(scene, f"s:{self.hot}") if hot else None
        self._paint_label(scene, hot, at or (0, 0))
        scene.after_idle(self._raise, scene)

    def _at(self, scene, name: str):
        item = self._items.get(name)
        return tuple(scene.coords(item)) if item is not None else None

    def _raise(self, scene) -> None:
        try:
            scene.tag_raise(TAG)
            scene.tag_raise("crypt-skull")
            scene.tag_raise("crypt-label")
        except Exception:
            return

    def _image(self, scene, name: str, key: tuple, at, anchor: str, card) -> None:
        photo = self._photo(scene, key)
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            tags = (TAG, "crypt-skull") if card else (TAG,)
            item = self._items[name] = scene.create_image(0, 0, image=photo, anchor=anchor, tags=tags)
            if card:
                scene.tag_bind(item, "<Enter>", lambda _e, c=card: self._hover(c))
                scene.tag_bind(item, "<Leave>", lambda _e, c=card: self._hover(None, c))
                scene.tag_bind(item, "<Button-1>", lambda _e, c=card: (self.open_card(c), "break")[1])
        elif self._keys.get(name) != key:
            scene.itemconfigure(item, image=photo)
        self._keys[name] = key
        scene.coords(item, round(at[0]), round(at[1]))

    def _hover(self, card: str | None, leaving: str | None = None) -> None:
        if card is not None or self.hot == leaving:
            self.hot = card

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            kind, s = key[0], key[-1]
            if kind == "plaque":
                image = art.plaque(key[1], s)
            else:
                image = art.niche(key[1]) if kind == "niche" else art.skull(key[1])
                image = image.resize((image.width * s, image.height * s), Image.NEAREST) if s > 1 else image
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)

    def _paint_label(self, scene, row: dict | None, at) -> None:
        """The hovered skull's card: its title and how long it has been forgotten, on a parchment above it."""
        key = None if row is None else (row["id"], round(at[0]), round(at[1]))
        if key == self._label_key:
            return
        self._label_key = key
        for item in self._label:
            scene.delete(item)
        self._label = []
        if row is None:
            return
        from PIL import ImageTk

        from cli_avatars.app.courier_art import note

        why = "archived, not done" if row["why"] == "archived" else "no update"
        lines = (row["title"][:60] or "(untitled)", f"Forgotten {row['days']} d · {why}", "Click to open the card.")
        width, x, y = 280, at[0], at[1] - 26
        texts = []
        top = 0.0
        for n, text in enumerate(lines):
            item = scene.create_text(x - width / 2 + 18, top, text=text, anchor="nw", width=width - 36,
                                     fill=("#3a2414", "#8a1c2a", "#7a5a3a")[n], font="DungeonBubble",
                                     tags=(TAG, "crypt-label"))
            box = scene.bbox(item)
            top = (box[3] if box else top + 14) + 3
            texts.append(item)
        height = int(top) + 30
        for item in texts:
            scene.move(item, 0, y - height + 14)
        photo = self._photos[("label", height)] = ImageTk.PhotoImage(note(width, height), master=scene)
        back = scene.create_image(x, y - height, image=photo, anchor="n", tags=(TAG, "crypt-label"))
        scene.tag_lower(back, texts[0])
        self._label = [back, *texts]
