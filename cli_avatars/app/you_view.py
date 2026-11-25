"""YOU-AVATAR on the Dungeon floor (docs/you-avatar.md): Daniel's keeper and the bubbles of who needs him.

``Hall.place`` calls ``update`` first each frame: the keeper's spot (saved, else the throne room), held arrow or WASD
keys while it is selected, the camera following it while it walks, and who needs Daniel (``you_needs.who``) read at
most every ``READ_S``. A click on the floor walks it there through the doors; a click on it selects it, Esc lets go.
``paint`` draws the keeper, its ring and count badge, and a bobbing kind-coloured bubble over each needing avatar.
A click on a bubble, or walking up to that avatar, opens its row as the Needs you tab does. A bubble that comes from
the hook state alone plays ``arrive`` (rows already ring ``arrive`` or ``decide``); cues wait while a task is in focus.
"""

from __future__ import annotations

import logging
import sys

import focus
import needs_you
from cli_avatars.app import cues
from cli_avatars.app import you_art as art
from cli_avatars.app import you_walk as walk
from cli_avatars.app.av_roster import USER_ID
from cli_avatars.app.throttle import StoreThrottle
from cli_avatars.app.you_needs import COLOURS, GLYPHS, Need, near, who

TAG, BUBBLE = "you-keeper", "you-bubble"
READ_S = 1.0
HOLD_S = 0.6
REACH = 1.8
LEAVE = 2.8
MOVED_S = 1.0
FOLLOW = 6.0
SAVE_S = 1.0
_log = logging.getLogger("cli_avatars.you")


def view_for(book) -> "YouView":
    found = getattr(book, "_you", None)
    if found is None:
        found = book._you = YouView(book)
    return found


def _book(app):
    return getattr(app, "places", None)


def update(book, hall, plan, agents: dict, topics, cards, now: float) -> None:
    try:
        view_for(book).update(hall, plan, agents, topics, cards, now)
    except Exception:
        _log.debug("you update failed", exc_info=True)


def needs(book) -> dict[str, Need]:
    view = getattr(book, "_you", None)
    return dict(view.needs) if view is not None else {}


def public(book, body: dict | None) -> dict:
    """PHONE: the roster rows' extras with each needing avatar's ``need`` kind and the keeper's ``badge``."""
    out = {aid: dict(row) for aid, row in (body or {}).items()}
    found = needs(book)
    for aid, need in found.items():
        out.setdefault(aid, {})["need"] = need.kind
    out.setdefault(USER_ID, {})["badge"] = len(found)
    return out


def rest(book, floor) -> tuple[tuple[float, float], int]:
    """Where the keeper stands between walks."""
    view = getattr(book, "_you", None)
    if view is None or view.feet is None:
        return floor.centre(), 1
    return view.feet, view.face


def paint(book, scene, hall, now: float) -> bool:
    try:
        return view_for(book).paint(scene, hall, now)
    except Exception:
        _log.debug("you paint failed", exc_info=True)
        return False


def key(app, event) -> bool:
    """A key on the floor: True when the selected keeper took it (the camera does not pan)."""
    book = _book(app)
    return book is not None and view_for(book).key(str(getattr(event, "keysym", "")))


def key_up(app, event) -> None:
    book = _book(app)
    if book is not None:
        view_for(book).held.pop(str(getattr(event, "keysym", "")).lower(), None)


def click(app, event, inside=None) -> bool:
    """A click on the floor: a bubble opens its row, the keeper toggles selection, empty floor walks it there."""
    book = _book(app)
    return book is not None and view_for(book).click(event.x, event.y, inside)


class YouView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.room: str | None = None
        self.feet: tuple[float, float] | None = None
        self.face = 1
        self.selected = False
        self.held: dict[str, float] = {}
        self.needs: dict[str, Need] = {}
        self.moved_at = float("-inf")
        self._now = 0.0
        self._hall = None
        self._read = StoreThrottle(READ_S)
        self._seen: set[str] | None = None
        self._opened: set[str] = set()
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._bubbles: dict[str, tuple[float, float, float, float]] = {}
        self._box: tuple[float, float, float, float] | None = None
        self._save_at: float | None = None
        self._following = False

    # --- state -------------------------------------------------------------------------------------
    def _directory(self):
        directory = getattr(self.app, "_chat_directory", None)
        return directory() if callable(directory) else None

    def update(self, hall, plan, agents: dict, topics, cards, now: float) -> None:
        dt = 0.0 if not self._now else min(0.25, max(0.0, now - self._now))
        self._now, self._hall = now, hall
        layout = getattr(getattr(self.book._scene(), "_rooms_painter", None), "layout", None)
        if self.feet is None or plan.floor(self.room or "") is None:
            root = self._directory()
            found = walk.spot(plan, layout, walk.load(root) if root is not None else None)
            if found is None:
                return
            self.room, self.feet = found
            hall._sent[USER_ID] = self.room
        sent = hall._sent.get(USER_ID)
        trip = hall._trips.get(USER_ID)
        if sent and sent != self.room and plan.floor(sent) is not None:
            self.room = sent
            self.feet = trip[0][-1] if trip else plan.floor(sent).centre()
            self._save_at = now
        self._keys_step(hall, plan, dt, now)
        if trip is not None:
            self.moved_at = now
        self._read_needs(topics, cards, agents, now)
        self._approach(hall, now)
        self._follow(hall, plan, now, dt)
        if self._save_at is not None and now - self._save_at >= SAVE_S and trip is None:
            root = self._directory()
            if root is not None and self.room:
                walk.save(root, self.room, self.feet)
            self._save_at = None

    def _keys_step(self, hall, plan, dt: float, now: float) -> None:
        self.held = {k: t for k, t in self.held.items() if now - t <= HOLD_S}
        way = walk.heading(set(self.held)) if self.selected else None
        if way is None or dt <= 0.0:
            return
        hall._trips.pop(USER_ID, None)
        self._walk_keys(plan, way, walk.SPEED * dt, now)

    def _walk_keys(self, plan, way, dist: float, now: float) -> None:
        self.feet = walk.step(plan, self.feet, way, dist)
        self.face = walk.facing(way, self.face)
        room = plan.room_at(*self.feet)
        floor = plan.floor(room or "")
        if floor is not None and not floor.corridor and room != self.room:
            self.room = room
            self._hall._sent[USER_ID] = room
        self.moved_at = now
        self._save_at = now

    def _read_needs(self, topics, cards, agents: dict, now: float) -> None:
        def load():
            root = self._directory()
            if root is None:
                return [], {}
            from decisions import list_decisions

            items = needs_you.pending(root)
            task = focus.current(root)
            if task is not None:
                items = [r for r in items if focus.belongs(r, task)]
            askers = {str(r["id"]): str(r.get("from") or "") for r in list_decisions(root, open_only=True)}
            return items, askers

        try:
            items, askers = self._read.get(load, now)
        except Exception:
            items, askers = [], {}
        self.needs = who(items, topics, cards, agents, askers)
        fresh = set(self.needs) - (self._seen or set())
        quiet = self._seen is None
        self._seen = set(self.needs)
        if quiet or not any(self.needs[aid].item is None for aid in fresh):
            return
        root = self._directory()
        try:
            if root is not None and focus.current(root) is not None:
                return
        except Exception:
            return
        cues.play(self.app, "arrive")

    def _approach(self, hall, now: float) -> None:
        spots = {aid: hall._feet[aid] for aid in self.needs if aid in hall._feet}
        here = hall._feet.get(USER_ID)
        self._opened = {aid for aid in self._opened if aid in spots and near(here, {aid: spots[aid]},
                                                                             self.needs, LEAVE)}
        if now - self.moved_at > MOVED_S:
            return
        aid = near(here, spots, self.needs, REACH)
        if aid is not None and aid not in self._opened:
            self._opened.add(aid)
            self.open(aid)

    def _follow(self, hall, plan, now: float, dt: float) -> None:
        """While the keeper walks, ease the camera so it stays in the middle of the view."""
        scene = self.book._scene()
        camera = getattr(scene, "_camera", None)
        painter = getattr(scene, "_rooms_painter", None)
        walking = now - self.moved_at <= 0.05 or USER_ID in hall._trips
        if camera is None or painter is None or not walking:
            if self._following:
                self._following = False
                save = getattr(getattr(self.app, "dungeon", None), "_schedule_save", None)
                if callable(save):
                    save()
            return
        at = painter.to_canvas(*hall._where(plan, USER_ID, now)[0])
        if at is None:
            return
        self._following = True
        cx, cy = int(scene.winfo_width()) / 2.0, int(scene.winfo_height()) / 2.0
        k = min(1.0, max(dt, 0.05) * FOLLOW)
        if camera.move(round((cx - at[0]) * k), round((cy - at[1]) * k)):
            painter.paint(scene)

    def open(self, aid: str) -> None:
        """The row of ``aid``'s need, as the Needs you tab opens it; the avatar's chat when only its state waits."""
        need = self.needs.get(aid)
        if need is None:
            return
        if need.item is not None:
            from cli_avatars.app.needs_panel import open_item

            open_item(self.app, need.item)
            return
        av = getattr(self.app, "_inside", {}).get(aid)
        opener = getattr(self.app, "_open_chat_for_avatar", None)
        if av is not None and callable(opener):
            opener(av)

    # --- input -------------------------------------------------------------------------------------
    def key(self, keysym: str) -> bool:
        if keysym == "Escape" and self.selected:
            self.selected = False
            self.held.clear()
            return True
        name = keysym.lower()
        way = walk.direction(name)
        if way is None or not self.selected or self._hall is None:
            return False
        plan = self._hall.plan()
        if plan is None or self.feet is None:
            return False
        if name not in self.held:
            self._hall._trips.pop(USER_ID, None)
            self._walk_keys(plan, way, walk.TAP, self._now)
        self.held[name] = self._now
        return True

    def click(self, x: float, y: float, inside=None) -> bool:
        for aid, box in self._bubbles.items():
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                self.open(aid)
                return True
        box = self._box
        if box is not None and box[0] <= x <= box[2] and box[1] <= y <= box[3]:
            self.selected = not self.selected
            self.held.clear()
            return True
        if inside is not None:
            return False
        return self.walk_to(x, y)

    def walk_to(self, x: float, y: float) -> bool:
        """Walk the keeper to canvas ``(x, y)`` through the doors; False off the floor or on a clickable piece."""
        hall, scene = self._hall, self.book._scene()
        plan = hall.plan() if hall is not None else None
        painter = getattr(scene, "_rooms_painter", None)
        if plan is None or painter is None or self.feet is None or _clickable(scene, x, y):
            return False
        from cli_avatars.app.nav_widget import widget_for

        view = getattr(self.app, "dungeon", None)
        if view is not None and getattr(view, "scene", None) is scene and widget_for(view).hit(x, y) is not None:
            return False
        tile = painter.to_tile(x, y)
        room = plan.room_at(*tile) if tile is not None else None
        floor = plan.floor(room or "")
        if floor is None or not (floor.holds(*tile) or plan.walkable(*tile)):
            return False
        goal = floor.clamp(*tile) if not floor.corridor else tile
        now = self._now
        start = hall._where(plan, USER_ID, now)[0]
        path = plan.route(start, room, goal)
        hall._trips[USER_ID] = (path, now, now + hall._seconds(path))
        self.feet = goal
        if not floor.corridor:
            self.room = room
            hall._sent[USER_ID] = room
        self.moved_at = now
        self._save_at = now
        return True

    # --- drawing -----------------------------------------------------------------------------------
    def paint(self, scene, hall, now: float) -> bool:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None or plan is None or self.feet is None:
            self._drop(scene, set())
            return False
        scale = max(1, int(painter._scale))
        feet, face = hall._where(plan, USER_ID, now)
        if USER_ID not in hall._trips and now - self.moved_at > 0.05:
            face = self.face
        else:
            self.face = face
        at = painter.to_canvas(*feet)
        if at is None:
            return False
        walking = USER_ID in hall._trips or now - self.moved_at <= 0.15
        frame = int(now * (8 if walking else 2)) % (4 if walking else 2)
        x0, y0 = at[0] - 20 * scale, at[1] - art.FEET * scale
        keep = {"keeper"}
        if self.selected:
            keep.add("ring")
            self._image(scene, "ring", ("ring", scale, int(now * 4) % 4), (at[0], at[1]), "center")
        self._image(scene, "keeper", ("keeper", frame, walking, scale, face < 0), (x0, y0), "nw")
        self._box = (x0 + 10 * scale, y0 + 2 * scale, x0 + 32 * scale, y0 + 38 * scale)
        user = getattr(hall, "user", None)
        if user is not None:
            user.x, user.y = self._box[0], self._box[1]
            user.aw, user.ah = self._box[2] - self._box[0], self._box[3] - self._box[1]
        count = len(self.needs)
        if count:
            keep.add("badge")
            self._image(scene, "badge", ("badge", min(count, 10), max(2, scale)), (at[0] + 6 * scale, y0), "sw")
        self._paint_bubbles(scene, scale, now, keep)
        self._drop(scene, keep)
        return True

    def _paint_bubbles(self, scene, scale: int, now: float, keep: set[str]) -> None:
        import math

        size = max(2, scale)
        self._bubbles = {}
        for aid, need in sorted(self.needs.items()):
            av = getattr(self.app, "_inside", {}).get(aid)
            if av is None:
                continue
            label = getattr(av, "_label_box", None)
            top = min(av.y, label[1]) if label else av.y
            bob = round(math.sin(now * 4.0 + (hash(aid) % 7)) * 2 * size / 2)
            x, y = av.x + av.aw / 2.0, top - 2 + bob
            name = f"bubble:{aid}"
            keep.add(name)
            self._image(scene, name, ("bubble", COLOURS[need.kind], GLYPHS[need.kind], size), (x, y), "s")
            self._bubbles[aid] = (x - 7 * size, y - 15 * size, x + 7 * size, y)

    def _image(self, scene, name: str, key: tuple, at, anchor: str) -> None:
        photo = self._photo(scene, key)
        x, y = round(at[0]), round(at[1])
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            tags = (TAG, BUBBLE) if name.startswith("bubble") else (TAG,)
            item = self._items[name] = scene.create_image(x, y, image=photo, anchor=anchor, tags=tags)
        elif self._keys.get(name) != key:
            scene.itemconfigure(item, image=photo)
        scene.coords(item, x, y)
        scene.tag_raise(item)
        self._keys[name] = key

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import ImageTk

            kind = key[0]
            if kind == "keeper":
                image = art.keeper_frame(key[1], key[2], key[3], key[4])
            elif kind == "ring":
                image = art.ring(key[1], key[2])
            elif kind == "badge":
                image = art.badge(key[1], key[2])
            else:
                image = art.bubble(key[1], key[2], key[3])
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-64]:
                self._photos.pop(old)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)
        if "keeper" not in keep:
            self._box = None
            self._bubbles = {}


def _clickable(scene, x: float, y: float) -> bool:
    """A piece under the pointer with its own click (a courier, the boss, a plaque, the focus veil)."""
    try:
        for item in scene.find_overlapping(x, y, x, y):
            for tag in (str(item), *scene.gettags(item)):
                if tag not in (TAG, BUBBLE) and scene.tag_bind(tag, "<Button-1>"):
                    return True
    except Exception:
        return False
    return False
