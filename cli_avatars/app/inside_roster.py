"""AV.1 in the Dungeon: roster sprites, the user's avatar, and the needs-me walk.

``PlaceBook.draw_inside`` calls ``hall(book)`` each frame. The look and walk
rules live in ``av_roster`` and ``needs_walk`` so other views can share them.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from cli_avatars.app.av_roster import GROK, USER_ID, bot_hues, kind_of, look_for, roster_frame
from cli_avatars.app.needs_walk import Walker, beside, needing, read_rooms, stroll
from cli_avatars.app.room_fit import fit_inside
from cli_avatars.app.throttle import StoreThrottle
from cli_avatars.model.agent import AgentInfo
from cli_avatars.model.crossing import span

USER_SPOT = (0.0, 112.0)
STEP = 44
STROLL = 12


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
        x, y = self.user_spot()
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
