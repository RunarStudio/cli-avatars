"""TIMELAPSE on the Dungeon floor (docs/time-lapse.md): scrub the day and watch avatars walk room to room.

``paint`` runs from ``PlaceBook.draw_inside`` each frame. Off, it shows the TIME-LAPSE plate and keeps the room log.
On, it covers the live floor with the map tinted to the playhead's hour, draws each avatar of the day as a ghost in
its room (walking the real doors between frames) with fading trail motes, and the sundial bar at the bottom: ◄ day ►,
the sky band over 24 hours with a wine gem per chat moment, play/pause and speed, and LEAVE. A click on a gem, on a
ghost, or Enter opens that chat in the chat dock scrolled to the message at that time. Esc or LEAVE returns to the
live view. Canvas items are made once and changed in place; no window opens.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import focus
import timelapse
from board.model import PERSON
from cli_avatars.app import cues
from cli_avatars.app import timelapse_art as art
from cli_avatars.app import timelapse_ghosts as ghosts
from cli_avatars.app.session_rooms import APOTHECARY

TAG, ENTRY = "lapse", "lapse-entry"
K = 2
REFRESH_S = 2.0
RECORD_S = 5.0
TICK_S = 0.09
SPEEDS = (("x1", 4.0), ("x4", 16.0), ("x16", 64.0))
NIGHT = "#07060c"
_log = logging.getLogger("cli_avatars.timelapse")


def log(app) -> timelapse.Log:
    found = getattr(app, "_lapse_log", None)
    if found is None:
        found = app._lapse_log = timelapse.Log(app._chat_directory)
    return found


def lapse_for(book) -> "Lapse":
    found = getattr(book, "_lapse", None)
    if found is None:
        found = book._lapse = Lapse(book)
    return found


def paint(book, scene, now: float) -> None:
    try:
        lapse_for(book).paint(scene, now)
    except Exception:
        _log.debug("time-lapse paint failed", exc_info=True)


def cue(app, name: str, card: str | None = None) -> None:
    """Play ``name``; held while a task other than ``card`` is in focus."""
    held = focus.current(app._chat_directory())
    if held is None or held == card:
        cues.play(app, name)


def open_moment(app, moment: dict | None) -> bool:
    """Open the moment's chat in the chat dock, scrolled to the message at that time."""
    if not moment:
        return False
    try:
        app._show_chat(topic_id=moment["chat"])
    except Exception:
        return False
    window = getattr(app, "_chat_window", None)
    if callable(getattr(window, "see_at", None)):
        window.see_at(moment["ts"])
    cue(app, "moment", moment.get("card"))
    return True


def recorded_rows(app, rows: list[dict]) -> list[dict]:
    """Dungeon snapshot rows with the ids the logs use: ``daniel``, ``<source>:<first 8 of the session>``."""
    from cli_avatars.app.av_roster import USER_ID

    out = []
    for row in rows:
        if row.get("kind") == "subagent" or not row.get("room"):
            continue
        if row["id"] == USER_ID:
            out.append({**row, "id": PERSON})
            continue
        agent = getattr((getattr(app, "_inside", None) or {}).get(row["id"]), "agent", None)
        source, ident = getattr(agent, "source", ""), str(getattr(agent, "agent_id", "") or "")
        if source and ident:
            out.append({**row, "id": f"{source}:{ident.split(':')[-1][:8]}"})
    return out


class Lapse:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.on = False
        self.day = date.today()
        self.minute = 0.0
        self.playing = False
        self.speed = 0
        self.built: dict | None = None
        self._mark = None
        self._read_at = float("-inf")
        self._recorded = float("-inf")
        self._clock = None
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._ghosts: dict[int, str] = {}
        self._motes: list[int] = []
        self._bound = None
        self._hot = False
        self._dragging = False
        self._tick_at = 0.0
        self._bar = (0, 0, 1)
        self._scene = None

    # --- state -------------------------------------------------------------------------------------
    def start(self) -> None:
        self.on, self.playing, self.day = True, False, date.today()
        self.refresh(force=True)
        self.minute = self._first()
        cue(self.app, "tick")

    def leave(self) -> None:
        self.on = self.playing = False
        if self._scene is not None:
            self._clear(self._scene)

    def go(self, delta: int) -> None:
        day = timelapse.step(self.day, delta)
        if day != self.day:
            self.day, self.playing = day, False
            self.refresh(force=True)
            self.minute = self._first()
            cue(self.app, "tick")

    def seek(self, minute: float, tick: bool = True) -> None:
        minute = min(max(0.0, minute), self._end())
        if tick and abs(minute - self.minute) >= 1 and time.monotonic() - self._tick_at >= TICK_S:
            self._tick_at = time.monotonic()
            cue(self.app, "tick")
        self.minute = minute

    def hop(self, direction: int) -> None:
        """Jump to the previous or next frame."""
        marks = [f["minute"] for f in (self.built or {}).get("frames", [])]
        found = [m for m in marks if (m > self.minute + 0.01 if direction > 0 else m < self.minute - 0.01)]
        if found:
            self.seek(found[0] if direction > 0 else found[-1])

    def toggle_play(self) -> None:
        if not self.playing and self.minute >= self._end() - 0.5:
            self.minute = max(0.0, self._first() - timelapse.WALK_MIN)
        self.playing, self._clock = not self.playing, None

    def open_at(self, avatar: str | None = None) -> bool:
        if self.built is None:
            return False
        return open_moment(self.app, timelapse.moment(self.built, self.minute, avatar))

    def refresh(self, force: bool = False) -> None:
        directory = self.app._chat_directory()
        mark = (timelapse.stamp(directory), self.day) if self.day == date.today() or force else self._mark
        if not force and mark == self._mark:
            return
        painter = getattr(self._scene, "_rooms_painter", None)
        rooms = (getattr(painter, "layout", None) or {}).get("rooms") or []
        built = timelapse.safe_build(directory, self.day, rooms, APOTHECARY)
        if built is not None:
            self.built, self._mark = built, mark

    def _first(self) -> float:
        if self.day == date.today():
            return self._now_minute()
        frames = (self.built or {}).get("frames") or []
        return float(frames[0]["minute"]) if frames else 0.0

    def _end(self) -> float:
        return self._now_minute() if self.day == date.today() else 1439.0

    @staticmethod
    def _now_minute() -> float:
        t = time.localtime()
        return t.tm_hour * 60 + t.tm_min + t.tm_sec / 60.0

    # --- painting ----------------------------------------------------------------------------------
    def paint(self, scene, now: float) -> None:
        self._scene = scene
        self._record(now)
        self._bind(scene)
        w, h = max(200, int(scene.winfo_width())), max(200, int(scene.winfo_height()))
        if not self.on:
            self._clear(scene)
            self._image(scene, "entry", ("entry", self._hot), lambda: art.entry(self._hot), 8, h - 8, "sw",
                        (TAG, ENTRY), K)
            scene.tag_raise(ENTRY)
            return
        self._drop(scene, "entry")
        clock = time.monotonic()
        if self.playing:
            step = SPEEDS[self.speed][1] * min(0.25, clock - (self._clock or clock))
            self.minute = min(self.minute + step, self._end())
            self.playing = self.minute < self._end()
        self._clock = clock
        if self.day == date.today() and clock - self._read_at >= REFRESH_S:
            self._read_at = clock
            self.refresh()
        if self.built is None:
            self.refresh(force=True)
        rect = self._items.get("night")
        if rect is None or not scene.find_withtag(rect):
            rect = self._items["night"] = scene.create_rectangle(0, 0, w, h, fill=NIGHT, outline="", tags=(TAG,))
        scene.coords(rect, 0, 0, w, h)
        self._map(scene)
        ghosts.paint(self, scene, now)
        self._bar_paint(scene, w, h, now)
        scene.tag_raise(TAG)

    def _map(self, scene) -> None:
        painter = getattr(scene, "_rooms_painter", None)
        base = painter.base() if painter is not None and painter._scale else None
        if base is None:
            self._drop(scene, "map")
            return
        s, hour = int(painter._scale), int(self.minute // 60)
        key = ("map", id(base), hour, s)
        x = painter._center[0] - (base.width * s) // 2
        y = painter._center[1] - (base.height * s) // 2
        self._image(scene, "map", key, lambda: art.tint(base, hour * 60 + 30), x, y, "nw", (TAG,), s)

    def _bar_paint(self, scene, w: int, h: int, now: float) -> None:
        width = max(160, (w - 16) // K)
        x0, y0 = 8, h - 8 - art.BAR_H * K
        self._bar = (x0, y0, width)
        built = self.built or {"label": "", "day": self.day.isoformat(), "moments": [], "frames": []}
        kept = timelapse.days()
        title = self._title(built)
        moments = tuple(sorted({m["minute"] for m in built["moments"]}))
        busy = [0] * 96
        for frame in built["frames"]:
            busy[frame["minute"] // 15] += len(frame["doing"])
        today = self.day == date.today()
        key = ("bar", width, title, moments, tuple(busy), int(self._now_minute()) if today else None,
               self.day == kept[-1], self.day == kept[0])
        self._image(scene, "bar", key, lambda: art.bar(width, title, list(moments), busy,
                                                     self._now_minute() if today else None, key[6], key[7]),
                    x0, y0, "nw", (TAG,), K)
        px = x0 + art.track_x(self.minute, width) * K
        sand = int(now * 6) % 4 if self.playing else 1
        self._image(scene, "glass", ("glass", sand), lambda: art.glass(sand), px, y0 + 14 * K, "n", (TAG,), K)
        step = int(self.minute // 30)
        self._image(scene, "dial", ("dial", step), lambda: art.sundial(step), x0 + 3 * K, y0 + 3 * K, "nw",
                    (TAG,), K)
        for kind, box, look in (("play", art.play_box(width), "pause" if self.playing else "play"),
                                ("speed", art.speed_box(width), SPEEDS[self.speed][0])):
            self._image(scene, kind, ("btn", look), lambda look=look: art.button(look), x0 + box[0] * K,
                        y0 + box[1] * K, "nw", (TAG,), K)
        text = self._items.get("clock")
        words = f"{timelapse.clock(self.minute)}"
        if text is None or not scene.find_withtag(text):
            text = self._items["clock"] = scene.create_text(0, 0, text="", anchor="s", fill="#ffe6a0",
                                                            font=("Courier", 11, "bold"), tags=(TAG,))
        if scene.itemcget(text, "text") != words:
            scene.itemconfigure(text, text=words)
        scene.coords(text, px, y0 + 2)

    def _title(self, built: dict) -> str:
        when = date.fromisoformat(built["day"])
        name = f"{when:%a} {when.day} {when:%b}"
        return f"TIME-LAPSE - {built['label']} {name}" if built["label"] in ("Today", "Yesterday") else \
            f"TIME-LAPSE - {name}"

    # --- canvas helpers ----------------------------------------------------------------------------
    def _photo(self, scene, key: tuple, make, scale: int = 1):
        photo = self._photos.get(key)
        if photo is None:
            from PIL import Image, ImageTk

            image = make()
            if scale > 1:
                image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
            if len(self._photos) > 160:
                self._photos.clear()
            photo = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
        return photo

    def _image(self, scene, kind: str, key: tuple, make, x: float, y: float, anchor: str, tags: tuple,
               scale: int = 1) -> None:
        item = self._items.get(kind)
        if item is None or not scene.find_withtag(item):
            item = self._items[kind] = scene.create_image(x, y, anchor=anchor, tags=tags,
                                                          image=self._photo(scene, key, make, scale))
            self._keys[kind] = key
        elif self._keys.get(kind) != key:
            scene.itemconfigure(item, image=self._photo(scene, key, make, scale))
            self._keys[kind] = key
        if tuple(scene.coords(item)) != (float(x), float(y)):
            scene.coords(item, x, y)

    def _drop(self, scene, kind: str) -> None:
        item = self._items.pop(kind, None)
        self._keys.pop(kind, None)
        if item is not None:
            scene.delete(item)

    def _clear(self, scene) -> None:
        for kind in [k for k in self._items if k != "entry"]:
            self._drop(scene, kind)
        for item in self._motes:
            scene.delete(item)
        self._motes, self._ghosts = [], {}

    def _record(self, now: float) -> None:
        if now - self._recorded < RECORD_S:
            return
        self._recorded = now
        snapshot = getattr(getattr(self.book, "_hall", None), "snapshot", None)
        if snapshot:
            log(self.app).rooms(recorded_rows(self.app, snapshot[1]))

    # --- input -------------------------------------------------------------------------------------
    def _bind(self, scene) -> None:
        """A bindtag of our own ahead of the scene's: while on, clicks and keys stop here (no pan, no drag-out)."""
        if self._bound is scene:
            return
        self._bound = scene
        if TAG not in scene.bindtags():
            scene.bindtags((TAG,) + tuple(scene.bindtags()))
        scene.bind_class(TAG, "<Button-1>", lambda e: self.press(e.x, e.y))
        scene.bind_class(TAG, "<B1-Motion>", lambda e: self.drag(e.x, e.y))
        scene.bind_class(TAG, "<ButtonRelease-1>", lambda _e: self._release())
        scene.bind_class(TAG, "<Motion>", lambda e: self._motion(e.x, e.y))
        scene.bind_class(TAG, "<KeyPress>", self.key)

    def press(self, x: float, y: float) -> str | None:
        if self.on:
            return self.click(x, y)
        if self._on_entry(x, y):
            self._hover(self._scene, False)
            self.start()
            self._scene.focus_set()
            return "break"
        return None

    def _on_entry(self, x: float, y: float) -> bool:
        item = self._items.get("entry")
        box = self._scene.bbox(item) if item is not None and self._scene is not None else None
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def _motion(self, x: float, y: float) -> None:
        if not self.on and self._scene is not None and self._on_entry(x, y) != self._hot:
            self._hover(self._scene, not self._hot)

    def _release(self) -> str | None:
        was, self._dragging = self._dragging, False
        return "break" if self.on or was else None

    def _hover(self, scene, hot: bool) -> None:
        self._hot = hot
        try:
            scene.config(cursor="hand2" if hot else "")
        except Exception:
            return

    def click(self, x: float, y: float) -> str | None:
        if not self.on:
            return None
        self._scene.focus_set()
        x0, y0, width = self._bar
        bx, by = (x - x0) / K, (y - y0) / K
        if 0 <= bx <= width and 0 <= by <= art.BAR_H:
            return self._bar_click(bx, by, width)
        for item in self._scene.find_overlapping(x - 2, y - 2, x + 2, y + 2):
            aid = self._ghosts.get(item)
            if aid is not None:
                self.open_at(aid)
                return "break"
        return "break"

    def _bar_click(self, bx: float, by: float, width: int) -> str:
        built = self.built or {"label": "", "day": self.day.isoformat()}
        (pa, pb), (na, nb) = art.arrows(self._title(built))

        def inside(box) -> bool:
            return box[0] <= bx <= box[2] and box[1] <= by <= box[3]

        if by < 12 and pa <= bx <= pb:
            self.go(-1)
        elif by < 12 and na <= bx <= nb:
            self.go(1)
        elif inside(art.leave_box(width)):
            self.leave()
        elif inside(art.play_box(width)):
            self.toggle_play()
        elif inside(art.speed_box(width)):
            self.speed = (self.speed + 1) % len(SPEEDS)
        elif 8 <= by < art.BAND_Y and self._gem(bx, width) is not None:
            open_moment(self.app, self._gem(bx, width))
        elif by >= 8 and art.TRACK_X0 - 2 <= bx <= width - art.TRACK_RIGHT + 2:
            self._dragging = True
            self.seek(art.minute_at(bx, width))
        return "break"

    def _gem(self, bx: float, width: int) -> dict | None:
        found = [m for m in (self.built or {}).get("moments", []) if abs(art.track_x(m["minute"], width) - bx) <= 3]
        return min(found, key=lambda m: abs(art.track_x(m["minute"], width) - bx)) if found else None

    def drag(self, x: float, _y: float) -> str | None:
        if not (self.on and self._dragging):
            return None
        x0, _y0, width = self._bar
        self.seek(art.minute_at((x - x0) / K, width))
        return "break"

    def key(self, event) -> str | None:
        if not self.on:
            return None
        sym = event.keysym
        actions = {"Escape": self.leave, "space": self.toggle_play, "Left": lambda: self.go(-1),
                   "Right": lambda: self.go(1), "comma": lambda: self.hop(-1), "period": lambda: self.hop(1),
                   "Return": self.open_at, "plus": lambda: self._speed(1), "equal": lambda: self._speed(1),
                   "minus": lambda: self._speed(-1)}
        action = actions.get(sym)
        if action is None:
            return None
        action()
        return "break"

    def _speed(self, delta: int) -> None:
        self.speed = min(max(0, self.speed + delta), len(SPEEDS) - 1)

