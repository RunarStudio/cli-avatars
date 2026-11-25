"""MESSENGER on the Dungeon floor (docs/messenger.md): the courier walk, the seal flash, the lit card, the note.

``Hall.place`` calls ``update`` and ``paint`` each frame. At most every ``READ_S`` the view stores new couriers
(``messenger.sync``) and reads which wait and which cards are lit. One courier walks at a time, oldest first, from the
deciding task's room through the doors (the floor's own ``Plan.route``) to the affected task's room, eased in and out;
the rest queue (a ``+n`` pip rides on the walker). On arrival a wax seal flashes, the ``stamp`` cue plays, the store
marks it arrived and that room shows the task card glowing under a ``NEW FROM <room>`` ribbon until it is opened.
A click on the courier, the card or the ribbon opens the note: the decision, the answer and why it reached this task.
While a task is in focus a courier for another task holds still and its cues wait. Canvas items are made once and
changed in place.
"""

from __future__ import annotations

import logging
import math
import sys
import time

import focus
import messenger
from cli_avatars.app import courier_art as art
from cli_avatars.app import cues
from cli_avatars.app.room_floor import along, length, wander
from cli_avatars.app.session_rooms import APOTHECARY
from cli_avatars.app.throttle import StoreThrottle

TAG = "courier"
READ_S = 1.0
GAP_S = 0.8
FLASH_S = 0.9
MIN_WALK_S = 2.5
PACE = 0.8
PER_ROOM = 3
NOTE_W = 340
_log = logging.getLogger("cli_avatars.courier")


def view_for(book) -> "CourierView":
    found = getattr(book, "_courier", None)
    if found is None:
        found = book._courier = CourierView(book)
    return found


def update(book, hall, plan, now: float) -> None:
    try:
        view_for(book).update(hall, plan, now)
    except Exception:
        _log.debug("courier update failed", exc_info=True)


def paint(book, scene, hall, now: float | None = None) -> None:
    try:
        view_for(book).paint(scene, hall, time.time() if now is None else now)
    except Exception:
        _log.debug("courier paint failed", exc_info=True)


def rows(book) -> list[dict]:
    """PHONE: the walking courier as one roster row (map feet, facing, walking)."""
    view = getattr(book, "_courier", None)
    return view.public() if view is not None else []


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def room_of(plan, layout: dict | None, topic: str) -> str | None:
    """The room a task lives in (its topic's session room or built room), else the Apothecary, else the first."""
    name = focus.room_of((layout or {}).get("rooms") or [], topic or None, APOTHECARY)
    if plan.floor(name) is not None and not plan.floor(name).corridor:
        return name
    rooms = [f.name for f in plan.floors if not f.corridor]
    return rooms[0] if rooms else None


class Walk:
    def __init__(self, info: dict, path: list, seconds: float, now: float) -> None:
        self.info, self.path, self.seconds = info, path, seconds
        self.done, self.last, self.face = 0.0, now, 1

    def feet(self) -> tuple[tuple[float, float], int]:
        at, face = along(self.path, ease(self.done))
        self.face = face
        return at, face


class CourierView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.walk: Walk | None = None
        self.queued: list[dict] = []
        self.lit: dict[str, dict] = {}
        self.flashes: list[tuple[tuple[float, float], float]] = []
        self.note: dict | None = None
        self.held = False
        self._read = StoreThrottle(READ_S)
        self._next_at = 0.0
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._text: list[int] = []
        self._hot: str | None = None
        self._clicks: dict[str, str | None] = {}
        self._plan = None

    # --- state -------------------------------------------------------------------------------------
    def _directory(self):
        found = getattr(self.app, "_chat_directory", None)
        return found() if callable(found) else None

    def _inputs(self) -> tuple[list[dict], list[dict], str | None]:
        root = self._directory()
        if root is None:
            return [], [], None

        def load():
            messenger.sync(root)
            waiting = messenger.details(root, messenger.waiting(root))
            return ([r for r in waiting if r["state"] == messenger.WALKING],
                    [r for r in waiting if r["state"] == messenger.ARRIVED], focus.current(root))

        try:
            return self._read.get(load)
        except Exception:
            _log.debug("courier read failed", exc_info=True)
            return [], [], None

    def reread(self) -> None:
        self._read._ready = False

    def _holds(self, info: dict, task: str | None) -> bool:
        return task is not None and task not in (info["to"], info["from"])

    def update(self, hall, plan, now: float) -> None:
        self._plan = plan
        walking, arrived, task = self._inputs()
        self.lit = {}
        for info in arrived:
            self.lit.setdefault(info["to"], info)
        active = self.walk.info["key"] if self.walk else None
        self.queued = [r for r in walking if r["key"] != active]
        if self.walk is None and self.queued and now >= self._next_at and not self._holds(self.queued[0], task):
            self._start(hall, plan, self.queued.pop(0), now)
        self.held = self.walk is not None and self._holds(self.walk.info, task)
        if self.walk is not None:
            dt = min(0.5, max(0.0, now - self.walk.last))
            self.walk.last = now
            if not self.held:
                self.walk.done = min(1.0, self.walk.done + dt / self.walk.seconds)
            if self.walk.done >= 1.0:
                self._arrive(now)
        self.flashes = [f for f in self.flashes if now - f[1] < FLASH_S]
        from cli_avatars.app import courier_tiles

        courier_tiles.decorate(self.app, self.lit, self.open)

    def _start(self, hall, plan, info: dict, now: float) -> None:
        layout = getattr(getattr(self.book._scene(), "_rooms_painter", None), "layout", None)
        here, there = room_of(plan, layout, info["from_topic"]), room_of(plan, layout, info["to_topic"])
        if here is None or there is None:
            return
        start = wander(plan.floor(here), info["key"], now)[0]
        path = plan.route(start, there, self.spot(plan, there, 1.2))
        seconds = max(MIN_WALK_S, hall._seconds(path) * PACE) if length(path) > 0 else MIN_WALK_S
        self.walk = Walk({**info, "from_room": here, "to_room": there}, path, seconds, now)
        self._cue("rustle")

    def _arrive(self, now: float) -> None:
        walk, self.walk = self.walk, None
        self.flashes.append((walk.path[-1], now))
        self._next_at = now + GAP_S
        root = self._directory()
        try:
            if root is not None:
                messenger.mark(root, walk.info["key"], messenger.ARRIVED, now)
        except Exception:
            _log.debug("courier mark failed", exc_info=True)
        self.lit.setdefault(walk.info["to"], walk.info)
        self.reread()
        self._cue("stamp")

    def _cue(self, name: str) -> None:
        root = self._directory()
        try:
            if root is not None and focus.current(root) is not None and not self._focus_task_in(root):
                return
        except Exception:
            return
        cues.play(self.app, name)

    def _focus_task_in(self, root) -> bool:
        task = focus.current(root)
        walk = self.walk.info if self.walk else None
        return walk is not None and task in (walk["to"], walk["from"])

    def spot(self, plan, room: str, depth: float) -> tuple[float, float]:
        """Where the lit card hangs (``depth`` 0) or the courier stops: the middle of the room's back wall."""
        a, b, c, _d = plan.floor(room).box()
        return plan.floor(room).clamp((a + c) / 2.0, b + depth)

    def open(self, key: str) -> None:
        """The note for ``key`` on the floor; an arrived courier is marked opened, so its card stops glowing."""
        info = next((r for r in list(self.lit.values()) + self.queued if r["key"] == key), None)
        if info is None and self.walk is not None and self.walk.info["key"] == key:
            info = self.walk.info
        if info is None:
            return
        self.note = info
        view = getattr(self.app, "dungeon", None)
        if view is not None and getattr(view, "_center", "dungeon") != "dungeon":
            view.show_center("dungeon")
        root = self._directory()
        if root is not None and info["state"] == messenger.ARRIVED:
            messenger.mark(root, key, messenger.OPENED)
            self.lit.pop(info["to"], None)
            self.reread()

    def open_task(self) -> None:
        info, self.note = self.note, None
        view = getattr(self.app, "dungeon", None)
        panel = getattr(self.app, "_tasks_panel", None)
        if info is not None and view is not None:
            view.show_center("tasks")
            if panel is not None:
                panel.open_card(info["to"])

    def public(self) -> list[dict]:
        if self.walk is None or self._plan is None:
            return []
        (u, v), face = self.walk.feet()
        return [{"id": f"courier:{self.walk.info['key']}", "kind": "courier", "name": "Courier",
                 "room": self._plan.room_at(u, v), "feet": (u, v), "face": face, "walk": not self.held}]

    # --- drawing -----------------------------------------------------------------------------------
    def paint(self, scene, hall, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None or plan is None:
            self._drop(scene, set())
            return
        s = max(1, int(painter._scale))
        keep: set[str] = set()
        pulse = round((0.5 + 0.5 * math.sin(now * math.tau * 0.8)) * 7)
        by_room: dict[str, int] = {}
        layout = painter.layout or {}
        for card, info in sorted(self.lit.items(), key=lambda kv: -kv[1]["ts"]):
            room = room_of(plan, layout, info["to_topic"])
            if room is None or by_room.get(room, 0) >= PER_ROOM:
                continue
            n = by_room[room] = by_room.get(room, 0) + 1
            u, v = self.spot(plan, room, 0.2)
            at = painter.to_canvas(u + (n - 1) * 1.1, v)
            if at is None:
                continue
            x, y = at[0], at[1] - 4 * s
            hot = self._hot == info["key"]
            keep |= {f"halo:{card}", f"card:{card}", f"ribbon:{card}"}
            self._image(scene, f"halo:{card}", ("halo", pulse, s), (x, y + 4 * s), "center", None)
            self._image(scene, f"card:{card}", ("card", pulse, s), (x, y), "s", info["key"])
            words = f"new from {info.get('from_room') or room_of(plan, layout, info['from_topic']) or 'a room'}"
            self._image(scene, f"ribbon:{card}", ("ribbon", words, hot, s), (x, y - 22 * s), "s", info["key"])
        if self.walk is not None:
            (u, v), face = self.walk.feet()
            at = painter.to_canvas(u, v)
            if at is not None:
                step = int(self.walk.done * self.walk.seconds * 9) % art.STEPS
                keep.add("walker")
                self._image(scene, "walker", ("walker", step, not self.held, face, s), at, "s", self.walk.info["key"])
                if self.queued:
                    keep.add("pip")
                    self._image(scene, "pip", ("ribbon", f"+{len(self.queued)}", False, s),
                                (at[0], at[1] - art.H * s - 2), "s", self.walk.info["key"])
        for i, (spot, t0) in enumerate(self.flashes):
            at = painter.to_canvas(*spot)
            if at is not None:
                step = min(art.FLASH_STEPS - 1, int((now - t0) / FLASH_S * art.FLASH_STEPS))
                keep.add(f"flash:{i}")
                self._image(scene, f"flash:{i}", ("flash", step, s), (at[0], at[1] - 12 * s), "center", None)
        self._drop(scene, keep)
        self._paint_note(scene)
        if keep or self.note is not None:
            scene.after_idle(self._raise, scene)

    def _raise(self, scene) -> None:
        """After the frame's avatars and signs: the courier walks in front of them, the note over all."""
        try:
            scene.tag_raise(TAG)
        except Exception:
            return

    def _image(self, scene, name: str, key: tuple, at, anchor: str, click: str | None) -> None:
        photo = self._photo(scene, key)
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            item = self._items[name] = scene.create_image(0, 0, image=photo, anchor=anchor, tags=(TAG,))
            if click is not None:
                scene.tag_bind(item, "<Button-1>", lambda _e, n=name: self._click(n))
                scene.tag_bind(item, "<Enter>", lambda _e, n=name: self._hover(n))
                scene.tag_bind(item, "<Leave>", lambda _e: self._hover(None))
        elif self._keys.get(name) != key:
            scene.itemconfigure(item, image=photo)
        self._keys[name] = key
        self._clicks[name] = click
        scene.coords(item, round(at[0]), round(at[1]))
        scene.tag_raise(item)

    def _click(self, name: str) -> None:
        key = self._clicks.get(name)
        if key:
            self.open(key)

    def _hover(self, name: str | None) -> None:
        self._hot = self._clicks.get(name) if name else None

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            kind, s = key[0], key[-1]
            if kind == "walker":
                image = art.courier(key[1], key[2], key[3])
            elif kind == "halo":
                image = art.halo(key[1])
            elif kind == "card":
                image = art.card(key[1])
            elif kind == "ribbon":
                image = art.ribbon(key[1], key[2])
            elif kind == "flash":
                image = art.flash(key[1])
            else:
                image = art.note(NOTE_W, key[1])
            if s > 1 and kind != "note":
                image = image.resize((image.width * s, image.height * s), Image.NEAREST)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-64]:
                self._photos.pop(old)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep and n != "note"]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)

    def _paint_note(self, scene) -> None:
        info = self.note
        if info is None:
            for item in self._text + [self._items.pop("note", None)]:
                if item is not None:
                    scene.delete(item)
            self._text = []
            self._keys.pop("note", None)
            return
        x = max(NOTE_W / 2 + 8, scene.winfo_width() / 2)
        y = scene.winfo_height() / 2
        if "note" not in self._items or self._keys.get("note") != ("note", info["key"]):
            self._paint_note_text(scene, info, x, y)
        for item in [self._items["note"], *self._text]:
            scene.tag_raise(item)

    def _paint_note_text(self, scene, info: dict, x: float, y: float) -> None:
        """Lay the text out first, then unroll a parchment just tall enough under it, centred on the floor."""
        for item in self._text + [self._items.pop("note", None)]:
            if item is not None:
                scene.delete(item)
        left, wrap = x - NOTE_W / 2 + 18, NOTE_W - 76
        ink, dim, wine = "#3a2414", "#7a5a3a", "#8a1c2a"
        lines = [(f"FROM {(info.get('from_room') or info['from_topic'] or 'a room').upper()} · {info['from_title']}",
                  wine, "DungeonBubble", 2),
                 (info["question"] or "A decision", ink, "DungeonText", 2),
                 (f"Daniel: {info['answer'] or 'answered'}", ink, "DungeonText", 6),
                 (f"Why here: {info['reason']}", dim, "DungeonBubble", 8),
                 (f"Open {info['to_title'][:32]} ›", wine, "DungeonBubble", 0)]
        self._text, top = [], 0.0
        for text, colour, font, gap in lines:
            item = scene.create_text(left, top, text=text, anchor="nw", fill=colour, font=font, width=wrap,
                                     tags=(TAG, "courier-note"))
            self._text.append(item)
            box = scene.bbox(item)
            top = (box[3] if box else top + 14) + gap
        height = int(top) + 34
        y0 = max(4.0, y - height / 2)
        for item in self._text:
            scene.move(item, 0, y0 + 16)
        photo = self._photo(scene, ("note", height))
        self._items["note"] = scene.create_image(x, y0, image=photo, anchor="n", tags=(TAG, "courier-note"))
        self._keys["note"] = ("note", info["key"])
        scene.tag_lower(self._items["note"], self._text[0])
        go = self._text[-1]
        scene.addtag_withtag("courier-go", go)
        scene.tag_bind("courier-note", "<Button-1>", lambda _e: self._close())
        scene.tag_bind(go, "<Button-1>", lambda _e: (self.open_task(), "break")[1])

    def _close(self) -> None:
        self.note = None
