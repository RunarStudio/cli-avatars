"""BODY on the Dungeon floor (docs/body-language.md): poses, the walk to the bench or the door, benches, smoke, hover.

``Hall.place`` calls ``update`` each frame with the rooms plan: it reads the needs-you list and the thresholds at
most every ``READ_S``, maps every avatar to a pose (``body.states``), and walks a stuck one to a seat on its room's
bench and a waiting one to the inside of its door with the Hall's own trips through the doors. ``rest`` is where a
posed avatar stays and how fast a flowing one paces. ``photos`` gives ``_paint_inside`` the posed frames; ``paint``
draws the benches, the chimneys and the smoke, and the one-word tag on hover. Canvas items are made once and changed
in place. Cues (sigh, knock, crackle) wait while a task is in focus.
"""

from __future__ import annotations

import logging
import sys
import time

import focus
import needs_you
from cli_avatars.app import body_art as art
from cli_avatars.app import body_spots as spots
from cli_avatars.app import cues
from cli_avatars.app.body import IDLE, SLUMP, STRIDE, TAP, WORDS, Found, Runs, Shift, Thresholds, states
from cli_avatars.app.room_floor import wander
from cli_avatars.app.throttle import StoreThrottle

PROP, SMOKE, HOVER = "body-prop", "body-smoke", "body-tag"
READ_S = 2.0
PAUSE = {STRIDE: 0.12}
SMOKE_HZ = 8.0
SMOKE_FADE = 0.8
WALL_PX = 30
BRAZIER_PX = 14
CUE_GAP_S = 1.2
_log = logging.getLogger("cli_avatars.body")


def view_for(book) -> "BodyView":
    found = getattr(book, "_body", None)
    if found is None:
        found = book._body = BodyView(book)
    return found


def update(book, hall, plan, agents: dict, topics, cards, now: float) -> set[str]:
    """Ids walked or held by a pose this frame; the needs-me walk leaves them alone."""
    try:
        return view_for(book).update(hall, plan, agents, topics, cards, now)
    except Exception:
        _log.debug("body update failed", exc_info=True)
        return set()


def rest(book, floor, aid: str, now: float) -> tuple[tuple[float, float], int]:
    """Where ``aid`` stands between trips: its bench seat or door spot, else its pace (brisker while flowing)."""
    view = getattr(book, "_body", None)
    if view is None:
        return wander(floor, aid, now)
    held = view.targets.get(aid)
    if held is not None:
        return held[1], held[2]
    pose, was, k = view.blend.get(aid, (IDLE, IDLE, 1.0))
    here = wander(floor, aid, now, PAUSE.get(pose, 0.5))
    if k >= 1.0 or PAUSE.get(was, 0.5) == PAUSE.get(pose, 0.5):
        return here
    there = wander(floor, aid, now, PAUSE.get(was, 0.5))[0]
    return (there[0] + (here[0][0] - there[0]) * k, there[1] + (here[0][1] - there[1]) * k), here[1]


def photos(book, aid: str, av, shown, look, scale: int, now: float):
    """``shown`` with this avatar's pose drawn in; the same object while it is idle or no rooms show."""
    view = getattr(book, "_body", None)
    if view is None or look is None:
        return shown
    pose, was, k = view.blend.get(aid, (IDLE, IDLE, 1.0))
    if pose == IDLE and (was == IDLE or k >= 1.0):
        return shown
    phase = {STRIDE: int(now * 5) % 4, TAP: int(now * 6) % 4, SLUMP: int(now * 4) % 8}.get(pose, 0)
    sig = (pose, was, round(k * 4) / 4, phase)
    if getattr(av, "_body_sig", None) != sig:
        av._body_sig = sig
        av._draw_sig = None
    return PosePhotos(shown, look, scale, getattr(av, "dir", 1) < 0, sig)


class PosePhotos:
    """The roster cache with the pose bent into each frame at native pixels, then scaled whole."""

    def __init__(self, inner, look, scale: int, mirror: bool, sig: tuple) -> None:
        self._inner, self._look, self._scale, self._mirror, self._sig = inner, look, scale, mirror, sig

    def get(self, key: tuple, factory):
        from PIL import Image

        from cli_avatars.app.av_roster import roster_frame

        pose, was, k, phase = self._sig

        def make():
            square = roster_frame(factory(), self._look, 1, self._mirror)
            bent = art.posed(square, pose, was, k, phase, -1 if self._mirror else 1)
            side = bent.width * max(1, self._scale)
            return bent.resize((side, side), Image.NEAREST)

        photos = getattr(self._inner, "_photos", None)
        tail = ("body", self._look, self._scale, self._mirror, pose, was, k, phase)
        if photos is not None:
            return photos.get(tuple(key) + tail, make)
        return make()


class BodyView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.runs, self.shift = Runs(), Shift()
        self.found = Found({}, {})
        self.blend: dict[str, tuple[str, str, float]] = {}
        self.targets: dict[str, tuple[str, tuple[float, float], int]] = {}
        self.benches: dict[str, tuple[tuple[float, float], int]] = {}
        self.shown: dict[str, float] = {}
        self._read = StoreThrottle(READ_S)
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._smoking: set[str] | None = None
        self._cue_at = float("-inf")
        self._last = None
        self._bound = None
        self._hover: str | None = None

    # --- state -------------------------------------------------------------------------------------
    def _inputs(self) -> tuple[list, Thresholds]:
        directory = getattr(self.app, "_chat_directory", None)
        if not callable(directory):
            return [], Thresholds()

        def load():
            from cli_avatars.app.body import thresholds_in

            root = directory()
            return needs_you.pending(root), thresholds_in(root)

        try:
            return self._read.get(load)
        except Exception:
            return [], Thresholds()

    def update(self, hall, plan, agents: dict, topics, cards, now: float) -> set[str]:
        items, th = self._inputs()
        homes = {aid: hall.room_of(aid) for aid in agents}
        self.found = states(agents, topics, cards, items, homes, self.runs, now, th)
        self.blend = {aid: self.shift.see(aid, pose, now) for aid, pose in self.found.poses.items()}
        self.shift.keep(set(self.found.poses))
        targets = self._targets(plan, hall, homes)
        for aid in set(targets) | set(self.targets):
            new, old = targets.get(aid), self.targets.get(aid)
            if new is not None and (old is None or new[1] != old[1]):
                start = hall._feet.get(aid) or hall._where(plan, aid, now)[0]
                path = plan.route(start, new[0], new[1])
                hall._trips[aid] = (path, now, now + hall._seconds(path))
            elif new is None and aid in agents:
                hall.move(aid, homes[aid], now, keep=False)
        self.targets = targets
        self._cues(now)
        return set(targets)

    def _targets(self, plan, hall, homes: dict) -> dict:
        from cli_avatars.app.inside_roster import USER_ID

        layout = getattr(getattr(self.book._scene(), "_rooms_painter", None), "layout", None) or {}
        rooms = {r.get("name"): r for r in layout.get("rooms") or [] if isinstance(r, dict)}
        toward = hall.room_of(USER_ID)
        out, benches = {}, {}
        by_room: dict[tuple[str, str], list[str]] = {}
        for aid, pose in sorted(self.found.poses.items()):
            room = homes.get(aid)
            if pose in (SLUMP, TAP) and room and plan.floor(room) is not None and not plan.floor(room).corridor:
                by_room.setdefault((room, pose), []).append(aid)
        for name, room in rooms.items():
            sitters = by_room.get((name, SLUMP), [])
            corner = spots.bench(room, len(sitters))
            if corner is not None:
                benches[name] = (corner, max(spots.SEATS, len(sitters)))
                first = (max(spots.SEATS, len(sitters)) - len(sitters)) / 2.0
                for i, aid in enumerate(sitters):
                    out[aid] = (name, plan.floor(name).clamp(*spots.seat(corner, first + i)), 1)
            for i, aid in enumerate(by_room.get((name, TAP), [])):
                found = spots.door(plan, name, toward, i, room)
                if found is not None:
                    out[aid] = (name, found[0], found[1])
        self.benches = benches
        return out

    def _cues(self, now: float) -> None:
        smoking = set(self.found.smoke)
        names = [{SLUMP: "sigh", TAP: "knock"}.get(pose) for _aid, _was, pose in self.shift.changed()]
        if self._smoking is not None and smoking - self._smoking:
            names.append("crackle")
        self._smoking = smoking
        names = [n for n in names if n]
        if not names or now - self._cue_at < CUE_GAP_S:
            return
        directory = getattr(self.app, "_chat_directory", None)
        try:
            if callable(directory) and focus.current(directory()) is not None:
                return
        except Exception:
            return
        self._cue_at = now
        cues.play(self.app, names[0])

    def word(self, aid: str) -> str:
        return WORDS[self.found.poses.get(aid, IDLE)]

    def public(self, homes: dict) -> dict[str, dict]:
        """PHONE: each avatar's pose and its room's smoke, for the roster snapshot."""
        return {aid: {"pose": pose, "smoke": self.found.smoke.get(homes.get(aid), 0.0)}
                for aid, pose in self.found.poses.items()}

    # --- drawing -----------------------------------------------------------------------------------
    def paint(self, scene, hall, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None or hall.plan() is None:
            self._drop(scene, set())
            return
        scale = max(1, int(painter._scale))
        dt = 0.0 if self._last is None else min(0.5, max(0.0, now - self._last))
        self._last = now
        keep: set[str] = set()
        for name, (corner, seats) in self.benches.items():
            at = painter.to_canvas(*corner)
            if at is not None:
                keep.add(f"bench:{name}")
                self._image(scene, f"bench:{name}", ("bench", seats, scale), at, floor=True)
        layout = painter.layout or {}
        for room in layout.get("rooms") or []:
            name = room.get("name") if isinstance(room, dict) else None
            target = self.found.smoke.get(name, 0.0)
            level = self.shown.get(name, 0.0)
            level += (target - level) * min(1.0, dt / SMOKE_FADE * 3.0)
            if level < 0.02 and target == 0.0:
                self.shown.pop(name, None)
                continue
            self.shown[name] = level
            source = spots.smoke(room)
            at = painter.to_canvas(*source[1]) if source else None
            if at is None:
                continue
            lift = (WALL_PX if source[0] == "chimney" else BRAZIER_PX) * scale
            if source[0] == "chimney":
                keep.add(f"chimney:{name}")
                self._image(scene, f"chimney:{name}", ("chimney", round(level * 4), scale), (at[0], at[1] - lift))
                lift += 18 * scale
            keep.add(f"smoke:{name}")
            step = int(now * SMOKE_HZ) % art.SMOKE_STEPS
            self._image(scene, f"smoke:{name}", ("smoke", round(level * 10) / 10, step, scale), (at[0], at[1] - lift))
        self._drop(scene, keep)
        self._paint_hover(scene)

    def _image(self, scene, name: str, key: tuple, at: tuple[float, float], floor: bool = False) -> None:
        photo = self._photo(scene, key)
        x, y = round(at[0]), round(at[1])
        if key[0] == "bench":
            x -= self._anchor(key[1])[0] * key[-1]
            y -= self._anchor(key[1])[1] * key[-1]
            anchor = "nw"
        else:
            anchor = "s"
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            tags = ("floor", PROP) if floor else (SMOKE,)
            item = self._items[name] = scene.create_image(x, y, image=photo, anchor=anchor, tags=tags)
            if floor:
                scene.tag_raise(item, "rooms")
        elif self._keys.get(name) != key:
            scene.itemconfigure(item, image=photo)
        scene.coords(item, x, y)
        if not floor:
            scene.tag_raise(item)
        self._keys[name] = key

    def _anchor(self, seats: int) -> tuple[int, int]:
        return art.bench(seats)[1]

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            kind, scale = key[0], key[-1]
            if kind == "bench":
                image = art.bench(key[1])[0]
            elif kind == "chimney":
                image = art.chimney(key[1] / 4)
            elif kind == "smoke":
                image = art.smoke(key[1], key[2])
            else:
                image = art.tag(key[1], key[2])
            if scale > 1:
                image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-96]:
                self._photos.pop(old)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep and not n.startswith("hover")]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)

    # --- hover -------------------------------------------------------------------------------------
    def _paint_hover(self, scene) -> None:
        if self._bound is not scene:
            self._bound = scene
            scene.bind("<Motion>", lambda e: self._motion(scene, e.x, e.y), add="+")
            scene.bind("<Leave>", lambda _e: self._motion(scene, -1, -1), add="+")
        av = self.app._inside.get(self._hover) if self._hover else None
        if av is None or self._hover not in self.found.poses:
            self._hide(scene)
            return
        word = self.word(self._hover)
        scale = max(1, int(getattr(scene._rooms_painter, "_scale", 1)))
        box = getattr(av, "_label_box", None)
        x = av.x + av.aw / 2.0
        y = box[1] - 2 if box else av.y - 16
        self._image(scene, "hover", ("tag", word.upper(), self.found.poses[self._hover], scale), (x, y))

    def _motion(self, scene, x: float, y: float) -> None:
        hit = None
        for aid, av in self.app._inside.items():
            if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah and aid in self.found.poses:
                if hit is None or av.y > self.app._inside[hit].y:
                    hit = aid
        self._hover = hit
        if hit is None:
            self._hide(scene)

    def _hide(self, scene) -> None:
        item = self._items.pop("hover", None)
        self._keys.pop("hover", None)
        if item is not None:
            try:
                scene.delete(item)
            except Exception:
                return


def paint(book, scene, hall, now: float | None = None) -> None:
    try:
        view_for(book).paint(scene, hall, time.time() if now is None else now)
    except Exception:
        _log.debug("body paint failed", exc_info=True)
