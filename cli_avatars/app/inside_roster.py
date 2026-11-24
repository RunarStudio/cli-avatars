"""AV.1 in the Dungeon: roster sprites, the user's avatar, and the needs-me walk.

``PlaceBook.draw_inside`` calls ``hall(book)`` each frame. The look and walk
rules live in ``av_roster`` and ``needs_walk`` so other views can share them.
With rooms painted (MOVE.1) every avatar, the user's too, belongs to one room:
it wanders on that floor and changes room only through the doors (``room_floor``).
"""

from __future__ import annotations

import time
import zlib
from contextlib import contextmanager
from dataclasses import replace

from cli_avatars.app.av_roster import GROK, USER_ID, base_hue, bot_hues, kind_of, look_for, roster_frame
from cli_avatars.app.needs_walk import Walker, beside, needing, read_rooms, stroll
from cli_avatars.app.room_fit import fit_inside
from cli_avatars.app.room_floor import Plan, along, length, wander
from cli_avatars.app.session_rooms import APOTHECARY, bound_room
from cli_avatars.app.throttle import StoreThrottle
from cli_avatars.model.agent import AgentInfo
from cli_avatars.model.crossing import span

USER_SPOT = (0.0, 112.0)
STEP = 44
STROLL = 12
USER_ROOM = "Apothecary"
FEET_UP = 0.08
SNAPSHOT_S = 0.2


def roster_rows(feet: dict, inside: dict, rooms: dict, hues: dict, walking: set) -> list[dict]:
    """PHONE.2: each avatar's feet in layout tiles, room and look, for the phone map. Plain data."""
    out = []
    for aid, spot in feet.items():
        av = inside.get(aid)
        agent = getattr(av, "agent", None)
        if aid != USER_ID and agent is None:
            continue
        kind = "user" if aid == USER_ID else kind_of(agent)
        row = {"id": aid, "kind": kind, "name": "You" if aid == USER_ID else str(getattr(agent, "name", "") or ""),
               "room": rooms.get(aid), "feet": (float(spot[0]), float(spot[1])),
               "face": -1 if getattr(av, "dir", 1) < 0 else 1, "walk": aid in walking}
        if kind == GROK:
            row["hue"] = hues.get(aid, base_hue(aid))
        out.append(row)
    return out


class RosterPhotos:
    """The shell cache with the roster square: native crop, body hue, whole scale."""

    def __init__(self, photos, look, scale: int, mirror: bool) -> None:
        self._photos = photos
        self._tail = ("av1", look, int(scale), bool(mirror))
        self._own: dict[tuple, object] = {}

    def get(self, key: tuple, factory):
        look, scale, mirror = self._tail[1:]
        make = lambda: roster_frame(factory(), look, scale, mirror)  # noqa: E731
        if self._photos is not None:
            return self._photos.get(tuple(key) + self._tail, make)
        if key not in self._own:
            self._own[key] = make()
        return self._own[key]


def dress(av, photos, room_scale: int, hues: dict[str, int]):
    """Box and photos for the roster look. No rooms painted keeps the desktop size."""
    if room_scale < 1:
        return fit_inside(av, photos, room_scale), None
    look = look_for(av.agent, hues)
    if getattr(av, "_av1_look", None) != look:
        av._av1_look = look
        av._draw_sig = None
    av._room_scale = room_scale
    av.aw = av.ah = look.size * room_scale
    return RosterPhotos(photos, look, room_scale, getattr(av, "dir", 1) < 0), look


@contextmanager
def wearing(av, look):
    """Draw with the roster sheet. The scanner's agent keeps its own skin."""
    real = av.agent
    if look is not None and real.skin != look.skin:
        av.agent = replace(real, skin=look.skin)
    try:
        yield
    finally:
        av.agent = real


def hall(book) -> "Hall":
    found = getattr(book, "_hall", None)
    if found is None:
        found = Hall(book)
        book._hall = found
    return found


class Hall:
    def __init__(self, book) -> None:
        from cli_avatars.app.crossing import speed

        self.book = book
        self.walker = Walker(speed=speed())
        self.hues: dict[str, int] = {}
        self.user = None
        self._read = StoreThrottle()
        self._plan = None
        self._trips: dict[str, tuple[list, float, float]] = {}
        self._feet: dict[str, tuple[float, float]] = {}
        self._sent: dict[str, str] = {}
        self._now = 0.0
        self.snapshot: tuple[float, list[dict]] | None = None

    def plan(self) -> Plan | None:
        """Rooms of the painted layout, or None while the plain floor shows."""
        painter = getattr(self.book._scene(), "_rooms_painter", None)
        layout = getattr(painter, "layout", None)
        if layout is None or self._scale() < 1 or not callable(getattr(painter, "to_canvas", None)):
            return None
        if self._plan is None or self._plan[0] is not layout:
            self._plan = (layout, Plan.from_layout(layout))
        return self._plan[1] if self._plan[1].floors else None

    def room_of(self, aid: str) -> str | None:
        plan = self.plan()
        if plan is None:
            return None
        if plan.floor(self._sent.get(aid, "")) is not None:
            return self._sent[aid]
        saved = self.book._file.rooms.get(aid) if hasattr(self.book, "_file") else None
        if plan.floor(saved or "") is not None:
            return saved
        if aid == USER_ID:
            return USER_ROOM if plan.floor(USER_ROOM) else plan.floors[-1].name
        av = self.book.app._inside.get(aid)
        agent = getattr(av, "agent", None)
        bound = bound_room(self._plan[0], agent)
        if plan.floor(bound or "") is not None:
            return bound
        if plan.floor(APOTHECARY) is not None:
            return APOTHECARY
        key = str(getattr(agent, "project", "") or aid) if getattr(agent, "source", "") == "bot" else aid
        return plan.floors[zlib.crc32(key.encode("utf-8")) % len(plan.floors)].name

    def home_room(self, aid: str) -> str | None:
        """DRAG.GLOW: the room ``aid`` was moved to, else the room it stands in, else its picked room."""
        plan = self.plan()
        if plan is None:
            return None
        saved = self.book._file.rooms.get(aid) if hasattr(self.book, "_file") else None
        if plan.floor(saved or "") is not None:
            return saved
        feet = self._feet.get(aid)
        return (plan.room_at(*feet) if feet is not None else None) or self.room_of(aid)

    def move(self, aid: str, room: str, now: float, keep: bool = True) -> bool:
        """Walk ``aid`` (or the user) to ``room`` through the doors; ``keep`` saves it as the chosen room."""
        plan = self.plan()
        floor = plan.floor(room) if plan is not None else None
        if floor is None or floor.corridor:
            return False
        start = self._feet.get(aid) or self._rest_at(plan, aid, now)[0]
        goal, path, eta = floor.centre(), [start], now
        for _ in range(3):
            goal = floor.centre() if aid == USER_ID else wander(floor, aid, eta)[0]
            path = plan.route(start, room, goal)
            eta = now + self._seconds(path)
        self._trips[aid] = (path, now, eta)
        self._sent[aid] = room
        set_room = getattr(self.book, "set_room", None)
        if keep and callable(set_room):
            set_room(aid, room)
        return True

    def drop(self, aid: str, x: float, y: float, now: float) -> bool:
        """A drag released on a room's floor at canvas ``(x, y)`` moves ``aid`` into that room."""
        plan = self.plan()
        tile = self.book._scene()._rooms_painter.to_tile(x, y) if plan is not None else None
        room = plan.room_at(*tile) if tile is not None else None
        if room is None or plan.floor(room).corridor:
            return False
        self._feet[aid] = plan.floor(room).clamp(*tile)
        self._trips.pop(aid, None)
        return self.move(aid, room, now)

    def user_box(self) -> tuple[float, float, float, float] | None:
        av = self.user
        if av is None:
            return None
        return (av.x, av.y, av.x + av.aw, av.y + av.ah)

    def user_feet(self, now: float | None = None) -> tuple[float, float] | None:
        plan = self.plan()
        if plan is None:
            return None
        return self._where(plan, USER_ID, self._now if now is None else now)[0]

    def place(self, spots: dict, now: float) -> dict:
        """Canvas spots for the settled avatars: room floors when rooms show, the ring otherwise."""
        plan = self.plan()
        if plan is None:
            return self.stroll(self.walk(spots, now), now)
        self._now = now
        inside = self.book.app._inside
        agents = {aid: inside[aid].agent for aid in spots if aid in inside}
        self.hues = bot_hues(aid for aid, agent in agents.items() if kind_of(agent) == GROK)
        topics, cards = self._rooms()
        need = set(needing(topics, cards, agents))
        user = self._where(plan, USER_ID, now)[0]
        self._feet[USER_ID] = user
        floor = plan.floor(self.room_of(USER_ID))
        order = sorted(need | (self.walker.walking() & set(spots)))
        homes = {aid: self._where(plan, aid, now) for aid in spots}
        paths = {}
        for index, aid in enumerate(order):
            if aid in homes:
                side = 1.375 * (1 if index % 2 == 0 else -1) * (index // 2 + 1)
                goal = floor.clamp(user[0] + side, user[1] - side)
                paths[aid] = plan.route(homes[aid][0], floor.name, goal)
        scale = max(1, self._scale())
        self.walker.step(need & set(spots), {aid: length(p) * scale for aid, p in paths.items()}, now)
        moved = {}
        for aid, (feet, face) in homes.items():
            t = self.walker.progress(aid)
            if t is not None and aid in paths:
                feet, face = along(paths[aid], t)
            self._feet[aid] = feet
            av = inside.get(aid)
            if av is None:
                continue
            av.frame, av.dir = int(now * 5), face
            moved[aid] = self._spot(feet, av)
        self._publish(plan)
        return moved

    def _publish(self, plan: Plan) -> None:
        """At most five times a second: who stands where, for the phone view's thread to read."""
        stamp = time.monotonic()
        last = self.snapshot
        if last is not None and stamp - last[0] < SNAPSHOT_S:
            return
        before = {row["id"]: row["feet"] for row in last[1]} if last is not None else {}
        feet = dict(self._feet)
        walking = {aid for aid, spot in feet.items() if before.get(aid) not in (None, spot)}
        rooms = {aid: plan.room_at(*spot) for aid, spot in feet.items()}
        self.snapshot = (stamp, roster_rows(feet, self.book.app._inside, rooms, self.hues, walking))

    def _where(self, plan: Plan, aid: str, now: float) -> tuple[tuple[float, float], int]:
        trip = self._trips.get(aid)
        if trip is not None:
            path, start, eta = trip
            if now < eta:
                return along(path, (now - start) / max(1e-6, eta - start))
            self._trips.pop(aid, None)
        return self._rest_at(plan, aid, now)

    def _rest_at(self, plan: Plan, aid: str, now: float) -> tuple[tuple[float, float], int]:
        floor = plan.floor(self.room_of(aid))
        return (floor.centre(), 1) if aid == USER_ID else wander(floor, aid, now)

    def _seconds(self, path) -> float:
        return length(path) * max(1, self._scale()) / max(1.0, self.walker.speed)

    def _spot(self, feet: tuple[float, float], av) -> tuple[float, float]:
        """Sprite centre whose feet stand on ``feet``."""
        painter = self.book._scene()._rooms_painter
        x, y = painter.to_canvas(*feet)
        size = look_for(av.agent, self.hues).size * max(1, self._scale())
        return (x, y - size * (0.5 - FEET_UP))

    def walk(self, spots: dict, now: float) -> dict:
        """Spots with every needing avatar moved toward its place beside the user."""
        inside = self.book.app._inside
        agents = {aid: inside[aid].agent for aid in spots if aid in inside}
        self.hues = bot_hues(aid for aid, agent in agents.items() if kind_of(agent) == GROK)
        topics, cards = self._rooms()
        need = set(needing(topics, cards, agents))
        user, gap = self.user_spot(), STEP * self._scale()
        order = sorted(need | (self.walker.walking() & set(spots)))
        goals = {aid: beside(user, index, gap) for index, aid in enumerate(order)}
        spans = {aid: span(*spots[aid], *goals[aid]) for aid in order if aid in spots}
        self.walker.step(need & set(spots), spans, now)
        moved = dict(spots)
        for aid in order:
            at = self.walker.at(aid, spots[aid], goals[aid]) if aid in spots else None
            if at is not None:
                moved[aid] = at
        return moved

    def stroll(self, spots: dict, now: float) -> dict:
        """Settled avatars pace near their spot; every one animates. Walkers keep their path."""
        inside = self.book.app._inside
        reach = STROLL * max(1, self._scale())
        moved = dict(spots)
        for aid, home in spots.items():
            av = inside.get(aid)
            if av is None:
                continue
            av.frame = int(now * 5)
            if aid not in self.walker.walking():
                moved[aid], av.dir = stroll(home, aid, now, reach)
        return moved

    def user_spot(self) -> tuple[float, float]:
        from cli_avatars.app.inside_spots import _box, _canvas

        scale = max(1, self._scale())
        return _canvas(USER_SPOT[0] * scale, USER_SPOT[1] * scale, _box(self.book))

    def paint_user(self, scene, photos, now: float) -> None:
        from cli_avatars.sprites.registry import REGISTRY
        from cli_avatars.world.avatar import Avatar

        if self.user is None:
            agent = AgentInfo(USER_ID, "You", source="user", skin="ember_mage")
            self.user = Avatar(agent, 800, 600, 0, REGISTRY, spring_mode=True)
        av = self.user
        av.frame = int(now * 5)
        shown, look = dress(av, photos, self._scale(), {})
        feet = self.user_feet(now) if self.plan() is not None else None
        x, y = self.user_spot() if feet is None else self._spot(feet, av)
        av.x, av.y = x - av.aw / 2.0, y - av.ah / 2.0
        with wearing(av, look):
            try:
                av.draw(scene, shown)
            except Exception:
                return

    def paint_marks(self, scene) -> None:
        """Amber mark over each avatar that waits for the user. Tag: ``inside-sub``."""
        from bubbles import blocked_indicator, place_blocked_mark
        from cli_avatars.app.render import photos_for

        scale = max(1, self._scale())
        photo = None
        for aid, av in self.book.app._inside.items():
            if not self.walker.marked(aid):
                continue
            if photo is None:
                photo = photos_for(self.book.app).get(("av1-need", scale), lambda: blocked_indicator(scale))
            x, y, _w, _h = place_blocked_mark((av.x + av.aw / 2.0 - 4.5 * scale, av.y, av.aw, av.ah), scale)
            try:
                scene.create_image(x, y, image=photo, anchor="nw", tags=("inside-sub",))
            except Exception:
                return

    def _rooms(self) -> tuple[list, list]:
        directory = getattr(self.book.app, "_chat_directory", None)
        if not callable(directory):
            return [], []
        try:
            return self._read.get(lambda: read_rooms(directory()))
        except Exception:
            return [], []

    def _scale(self) -> int:
        from cli_avatars.app.dungeon_rooms import rooms_scale

        scene = self.book._scene()
        return rooms_scale(scene) if scene is not None else 0
