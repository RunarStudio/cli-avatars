"""PARK.1 + IDLE-PROPS.1 + task routing on the Dungeon floor (docs/park.md).

``Hall.place`` calls ``update`` after BODY each frame. It reads the cards, the per-task CLI sessions and the
config at most every ``READ_S``; walks an avatar whose task chat or assigned card lives in another room to that
room (``task_route``), and a working one there to the room's task table; and holds a quiet avatar at an idle
object or a park station (``idle_life``) with the Hall's own trips through the doors. ``rest`` is where a held
avatar stays (a stroller keeps walking the park loop). ``paint`` draws the park's lights, the idle objects (a loop
while in use) and the task tables; canvas items are made once and changed in place. Cues (night, train) wait while
a task is in focus.
"""

from __future__ import annotations

import logging
import sys
import zlib

import focus
from cli_avatars.app import cues, idle_life, idle_props, park, still, task_route
from cli_avatars.app.throttle import StoreThrottle

FX, PROP, TABLE = "park-fx", "idle-prop", "task-table"
READ_S = 1.0
CONFIG_S = 2.0
FX_HZ = 6.0
PROP_HZ = 5.0
TRAIN_S = 1.4
TRAINING = ("hit", "spar", "lift")
_log = logging.getLogger("cli_avatars.life")


def view_for(book) -> "LifeView":
    found = getattr(book, "_life", None)
    if found is None:
        found = book._life = LifeView(book)
    return found


def update(book, hall, plan, agents: dict, posed: set, now: float) -> set[str]:
    """Ids held at an idle spot or a task table this frame; the needs-me walk leaves them alone."""
    try:
        return view_for(book).update(hall, plan, agents, posed, now)
    except Exception:
        _log.debug("life update failed", exc_info=True)
        return set()


def rest(book, aid: str, now: float):
    """``(feet, face)`` of a held avatar between trips, else None."""
    view = getattr(book, "_life", None)
    held = view.targets.get(aid) if view is not None else None
    if held is None:
        return None
    hold = view.holds.get(aid)
    station = view.stations.get(hold.oid) if hold is not None and hold.act == "stroll" else None
    if station is not None:
        from cli_avatars.app.room_floor import facing

        feet, ahead = park.stroll_at(station, zlib.crc32(aid.encode()), now)
        return feet, facing(feet, ahead)
    return held[1], held[2]


def public(book, body: dict | None) -> dict | None:
    """PHONE: each held avatar's idle act and object for the roster snapshot."""
    view = getattr(book, "_life", None)
    if view is None or not view.holds:
        return body
    out = {aid: dict(row) for aid, row in (body or {}).items()}
    for aid, hold in view.holds.items():
        out.setdefault(aid, {})["idle"] = {"act": hold.act, "oid": hold.oid, "tier": hold.tier}
    return out


def paint(book, scene, hall, now: float) -> None:
    try:
        view_for(book).paint(scene, hall, now)
    except Exception:
        _log.debug("life paint failed", exc_info=True)


class LifeView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.life = idle_life.Life()
        self.holds: dict[str, idle_life.Hold] = {}
        self.targets: dict[str, tuple[str, tuple[float, float], int]] = {}
        self.routes: dict[str, task_route.Route] = {}
        self.stations: dict[str, park.Station] = {}
        self.objs: list[idle_props.Obj] = []
        self.tables: dict[str, task_route.Table] = {}
        self.cfg = park.Settings()
        self._read = StoreThrottle(READ_S)
        self._config = StoreThrottle(CONFIG_S)
        self._began: dict[str, float] = {}
        self._arrive: dict[str, tuple[float, str]] = {}
        self._due: list[tuple[float, str]] = []
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}

    # --- state -------------------------------------------------------------------------------------
    def _inputs(self) -> tuple[list, dict]:
        directory = getattr(self.app, "_chat_directory", None)
        if not callable(directory):
            return [], {}

        def load():
            from cli_avatars.app import task_sessions
            from cli_avatars.app.orch_rooms import board_cards

            root = directory()
            return board_cards(root), task_sessions.load(root)

        try:
            return self._read.get(load)
        except Exception:
            return [], {}

    def _settings(self) -> park.Settings:
        directory = getattr(self.app, "_chat_directory", None)
        if not callable(directory):
            return park.Settings()
        try:
            return self._config.get(lambda: park.settings_in(directory()))
        except Exception:
            return park.Settings()

    def update(self, hall, plan, agents: dict, posed: set, now: float) -> set[str]:
        layout = hall._plan[0] if hall._plan else None
        cards, sessions = self._inputs()
        self.cfg = self._settings()
        self._route(hall, task_route.routes(cards, sessions, agents, layout), now)
        self.tables = task_route.tables(layout, cards)
        self.objs = idle_props.place(layout, self.cfg.props)
        self.stations = {s.oid: s for s in park.stations(layout)}
        working = {aid for aid in self.routes if getattr(agents.get(aid), "status", "") in idle_life.WORKING}
        homes = {aid: hall.room_of(aid) for aid in agents}
        self.holds = self.life.step(agents, homes, set(posed) | working, self.objs, list(self.stations.values()),
                                    self.cfg, now, plan)
        targets = {aid: (h.room, h.feet, h.face) for aid, h in self.holds.items()}
        targets.update(self._seats(working - set(posed)))
        for aid in set(targets) | set(self.targets):
            new, old = targets.get(aid), self.targets.get(aid)
            if new is not None and (old is None or new[1] != old[1]):
                start = hall._feet.get(aid) or hall._where(plan, aid, now)[0]
                goal = self._goal(aid, new[1], start, plan, hall, now, new[0])
                path = plan.route(start, new[0], goal)
                eta = now + hall._seconds(path)
                hall._trips[aid] = (path, now, eta)
                if new[0] == park.NAME:
                    self._arrive[aid] = (eta, self.holds[aid].act)
            elif new is None and aid in agents and aid not in posed:
                self._arrive.pop(aid, None)
                hall.move(aid, hall.room_of(aid), now, keep=False)
        self.targets = targets
        self._cues(now)
        return set(targets)

    def _route(self, hall, want: dict, now: float) -> None:
        """Walk each routed avatar to its card's room; a finished route sends it home unless moved by hand since."""
        for aid, route in want.items():
            if self.routes.get(aid) != route and hall.move(aid, route.room, now, keep=False):
                self._began[aid] = now
        for aid in [a for a in self.routes if a not in want]:
            began = self._began.pop(aid, now)
            if hall._manual.get(aid, float("-inf")) < began:
                hall._sent.pop(aid, None)
                hall.move(aid, hall.room_of(aid), now, keep=False)
        self.routes = {aid: r for aid, r in want.items() if aid in self._began}

    def _seats(self, working: set[str]) -> dict:
        out, by_room = {}, {}
        for aid in sorted(working):
            by_room.setdefault(self.routes[aid].room, []).append(aid)
        for room, aids in by_room.items():
            table = self.tables.get(room)
            if table is None:
                continue
            centre = (table.cell[0] + 0.5, table.cell[1] + 0.5)
            from cli_avatars.app.room_floor import facing

            for i, aid in enumerate(aids[:len(table.seats)]):
                out[aid] = (room, table.seats[i], facing(table.seats[i], centre))
        return out

    def _goal(self, aid, feet, start, plan, hall, now, room):
        hold = self.holds.get(aid)
        station = self.stations.get(hold.oid) if hold is not None and hold.act == "stroll" else None
        if station is None:
            return feet
        goal, key = feet, zlib.crc32(aid.encode())
        for _ in range(3):
            goal = park.stroll_at(station, key, now + hall._seconds(plan.route(start, room, goal)))[0]
        return goal

    def _cues(self, now: float) -> None:
        for aid, (at, act) in list(self._arrive.items()):
            if now >= at:
                self._arrive.pop(aid)
                self._due.append((at, "night"))
                if act in TRAINING:
                    self._due.append((at + TRAIN_S, "train"))
        ready = [name for at, name in self._due if now >= at]
        self._due = [(at, name) for at, name in self._due if now < at]
        if not ready:
            return
        directory = getattr(self.app, "_chat_directory", None)
        try:
            if callable(directory) and focus.current(directory()) is not None:
                return
        except Exception:
            return
        for name in dict.fromkeys(ready):
            cues.play(self.app, name)

    # --- drawing -----------------------------------------------------------------------------------
    def paint(self, scene, hall, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None or hall.plan() is None:
            self._drop(scene, set())
            return
        from cli_avatars.app import park_art

        scale = max(1, int(painter._scale))
        layout = painter.layout
        keep: set[str] = set()
        inputs = park_art.fx_inputs(layout)
        corner = painter._corner()
        if inputs is not None and corner is not None:
            box = inputs[0]
            at = (corner[0] + box[0] * scale, corner[1] + box[1] * scale)
            keep.add("fx")
            self._image(scene, "fx", ("fx", id(layout), int(now * FX_HZ) % park_art.FX_STEPS, scale), at, FX, inputs)
        taken = self.life.taken()
        for obj in self.objs:
            used = bool(taken.get(obj.oid)) and self._there(hall, taken[obj.oid])
            step = int(now * PROP_HZ) % 8 if used else 0
            keep.add(obj.oid)
            self._image(scene, obj.oid, ("prop", used, obj.kind, step, scale), painter.to_canvas(*obj.centre), PROP)
        for name, table in self.tables.items():
            centre = (table.cell[0] + 0.5, table.cell[1] + 0.5)
            key = ("table", min(3, len(table.doing)), min(3, len(table.todo)), min(1, table.blocked), scale)
            keep.add(f"table:{name}")
            self._image(scene, f"table:{name}", key, painter.to_canvas(*centre), TABLE)
        self._drop(scene, keep)

    def _there(self, hall, aids: list[str]) -> bool:
        return any(aid not in hall._trips for aid in aids)

    def _image(self, scene, name: str, key: tuple, at, tag: str, extra=None) -> None:
        if at is None:
            return
        photo, ax, ay = self._photo(scene, key, extra)
        x, y = round(at[0] - ax), round(at[1] - ay)
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            item = self._items[name] = scene.create_image(x, y, image=photo, anchor="nw", tags=("floor", tag))
            scene.tag_raise(item, "rooms")
        else:
            if self._keys.get(name) != key:
                scene.itemconfigure(item, image=photo)
            still.move(scene, item, x, y)
        self._keys[name] = key

    def _photo(self, scene, key: tuple, extra):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            from cli_avatars.app import idle_art, park_art

            scale = key[-1]
            if key[0] == "fx":
                image, ax, ay = park_art.fx(str(key[1]), key[2], *extra), 0, 0
            elif key[0] == "prop":
                sprite = idle_art.frame(key[2], key[1], key[3])
                image, ax, ay = sprite.image, sprite.ax, sprite.ay
            else:
                sprite = idle_art.table(key[1], key[2], key[3])
                image, ax, ay = sprite.image, sprite.ax, sprite.ay
            if scale > 1:
                image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
            found = self._photos[key] = (ImageTk.PhotoImage(image, master=scene), ax * scale, ay * scale)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-160]:
                self._photos.pop(old)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)
