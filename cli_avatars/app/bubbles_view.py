"""Talk bubbles, decision bubbles, and the blocked mark on the canvas."""

import logging
import time

from bubbles import blocked_indicator, integer_scale, place_blocked_mark, render_bubble
from decisions import open_agent_ids, place_open_decisions
from events import EventRejected

from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.model.agent import S
from cli_avatars.tuning import TUNING
from cli_avatars.world.avatar import Avatar

if HAS_PIL:
    try:
        from PIL import ImageTk
    except ImportError:
        HAS_PIL = False


def _draw_talk_bubbles(self):
    """Icon bubble above the sender. Subagent avatars are not in this map."""
    self.canvas.delete("talk_bubble")
    if not HAS_PIL:
        return
    scale = integer_scale(TUNING.avatar_scale)
    boxes = {
        aid: (av.x, av.y, av.aw, av.ah)
        for aid, av in self.avatars.items()
    }
    try:
        placed = self.scanner.bubbles.place(time.time(), boxes, scale)
    except Exception:
        logging.getLogger("cli_avatars.bubbles").exception("bubble layout failed")
        return
    cache = getattr(self, "_talk_cache", None)
    if cache is None or cache[0] != scale:
        cache = (scale, {})
        self._talk_cache = cache
    store = cache[1]
    photos = []
    for item in placed:
        key = (item.icon, item.typing_frame, scale, round(item.alpha, 2))
        photo = store.get(key)
        if photo is None:
            image = render_bubble(item.icon, scale, item.typing_frame, item.alpha)
            if image is None:
                continue
            photo = ImageTk.PhotoImage(image)
            store[key] = photo
        photos.append(photo)
        self.canvas.create_image(
            item.x, item.y, image=photo, anchor="nw", tags="talk_bubble",
        )
    self._talk_photos = photos


def _draw_decision_bubbles(self):
    """Decision icon while that avatar has an open decision.

    The glyph is the code placeholder in ``bubbles.decision_placeholder``
    (TODO(Caine art)). One bubble per avatar, on the top-right.
    """
    self.canvas.delete("decision_bubble")
    if not HAS_PIL:
        return
    scale = integer_scale(TUNING.avatar_scale)
    boxes = {
        aid: (av.x, av.y, av.aw, av.ah)
        for aid, av in self.avatars.items()
    }
    for subs in self.sub_avatars.values():
        for sv in subs:
            boxes[sv.agent.agent_id] = (sv.x, sv.y, sv.aw, sv.ah)
    try:
        agents = open_agent_ids(self._chat_directory(), timeout=0.05)
        placed = place_open_decisions(agents, boxes, scale)
    except EventRejected:
        return
    except Exception:
        logging.getLogger("cli_avatars.decisions").exception("decision bubble failed")
        return
    if not placed:
        return
    key = ("decision", scale)
    photo = self._decision_photo if getattr(self, "_decision_photo_key", None) == key else None
    if photo is None:
        image = render_bubble("decision", scale, 0, 1.0)
        if image is None:
            return
        photo = ImageTk.PhotoImage(image)
        self._decision_photo = photo
        self._decision_photo_key = key
    for _agent_id, x, y, _w, _h in placed:
        self.canvas.create_image(x, y, image=photo, anchor="nw", tags="decision_bubble")


def _draw_blocked_marks(self):
    """Amber '!' above an avatar whose state is blocked.

    The badge is a separate canvas image. It does not change the
    sprite cell (orchestrators stay 40×40, subagents 32×32).
    """
    self.canvas.delete("blocked_mark")
    if not HAS_PIL:
        return
    scale = integer_scale(TUNING.avatar_scale)
    boxes: list[tuple] = []

    def take(av: Avatar) -> None:
        if getattr(av.agent, "status", "") != S.BLOCKED:
            return
        boxes.append((av.x, av.y, av.aw, av.ah))

    for av in self.avatars.values():
        take(av)
    for subs in self.sub_avatars.values():
        for sv in subs:
            take(sv)
    for sv in getattr(self, "_lingering_subs", ()):
        take(sv)
    if not boxes:
        return
    key = ("blocked", scale)
    photo = self._blocked_photo if getattr(self, "_blocked_photo_key", None) == key else None
    if photo is None:
        image = blocked_indicator(scale)
        photo = ImageTk.PhotoImage(image)
        self._blocked_photo = photo
        self._blocked_photo_key = key
    for box in boxes:
        x, y, _w, _h = place_blocked_mark(box, scale)
        self.canvas.create_image(x, y, image=photo, anchor="nw", tags="blocked_mark")


class BubblesView:
    def __init__(self, app):
        self.app = app

    def step(self, frame=None):
        _draw_talk_bubbles(self.app)
        _draw_decision_bubbles(self.app)
        _draw_blocked_marks(self.app)
