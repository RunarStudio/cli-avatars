"""Talk bubbles, decision bubbles, and the blocked mark on the canvas."""

import logging
import time
from typing import Any

import recap
from bubbles import blocked_indicator, integer_scale, place_blocked_mark, render_bubble
from cli_avatars.app import decide_watch, focus_mode, mail_panel, needs_panel, recap_panel, standup_panel
from cli_avatars.app.activity_view import ActivityDraw
from cli_avatars.app.render import photos_for, sync_images
from cli_avatars.app.throttle import StoreThrottle
from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.model.agent import S
from cli_avatars.tuning import TUNING
from cli_avatars.world.avatar import Avatar
from decisions import open_agent_ids, place_open_decisions
from events import EventRejected

if HAS_PIL:
    try:
        from PIL import ImageTk as _ImageTk
    except ImportError:
        HAS_PIL = False
        _ImageTk = None
else:
    _ImageTk = None


def _ready() -> bool:
    return bool(HAS_PIL and _ImageTk is not None)


def _clear(self: Any, attr: str, ids: list) -> None:
    setattr(self, attr, sync_images(self.canvas, ids, []))


def _draw_talk_bubbles(self: Any, now: float | None = None) -> None:
    """Icon bubble above the sender. Subagent avatars are not in this map."""
    ids = list(getattr(self, "_talk_items", None) or [])
    if not _ready():
        _clear(self, "_talk_items", ids)
        self._talk_sig = None
        self._talk_photos = []
        self._bubble_hits = []
        return
    if now is None:
        now = time.time()
    scale = integer_scale(TUNING.avatar_scale)
    boxes = {
        aid: (av.x, av.y, av.aw, av.ah)
        for aid, av in self.avatars.items()
    }
    try:
        placed = self.scanner.bubbles.place(now, boxes, scale)
    except Exception:
        logging.getLogger("cli_avatars.bubbles").exception("bubble layout failed")
        _clear(self, "_talk_items", ids)
        self._talk_sig = None
        self._talk_photos = []
        self._bubble_hits = []
        return
    self._bubble_hits = [(item.x, item.y, item.w, item.h) for item in placed]
    sig = tuple(
        (item.icon, item.typing_frame, scale, round(item.alpha, 2), item.x, item.y)
        for item in placed
    )
    if sig == getattr(self, "_talk_sig", None) and len(ids) == len(placed):
        return
    cache = photos_for(self)
    photos = []
    rows = []
    for item in placed:
        key = ("talk", item.icon, item.typing_frame, scale, round(item.alpha, 2))
        photo = cache.get(
            key,
            lambda icon=item.icon, scale=scale, typing=item.typing_frame, alpha=item.alpha:
                render_bubble(icon, scale, typing, alpha),
        )
        if photo is None:
            continue
        photos.append(photo)
        rows.append((item.x, item.y, photo, "talk_bubble"))
    self._talk_items = sync_images(self.canvas, ids, rows)
    self._talk_photos = photos
    self._talk_sig = sig if len(rows) == len(placed) else None


def _open_agents(self: Any):
    """Open decision ids, read at most twice a second."""

    def load():
        try:
            return open_agent_ids(self._chat_directory(), timeout=0.05)
        except EventRejected:
            return None
        except Exception:
            logging.getLogger("cli_avatars.decisions").exception("decision bubble failed")
            return None

    # Separate from the HUD count cache. That value is an int; this one
    # is the asking-agent ids. Sharing the cache mixes the two.
    gate = getattr(self, "_decision_agents_read", None)
    if not isinstance(gate, StoreThrottle):
        gate = StoreThrottle()
        self._decision_agents_read = gate
    return gate.get(load)


def _draw_decision_bubbles(self: Any) -> None:
    """Decision icon while that avatar has an open decision.

    The glyph is the code placeholder in ``bubbles.decision_placeholder``
    (TODO(Caine art)). One bubble per avatar, on the top-right.
    """
    ids = list(getattr(self, "_decision_items", None) or [])
    if not _ready():
        _clear(self, "_decision_items", ids)
        self._decision_sig = None
        self._decision_hits = []
        return
    scale = integer_scale(TUNING.avatar_scale)
    boxes = {
        aid: (av.x, av.y, av.aw, av.ah)
        for aid, av in self.avatars.items()
    }
    for subs in self.sub_avatars.values():
        for sv in subs:
            boxes[sv.agent.agent_id] = (sv.x, sv.y, sv.aw, sv.ah)
    agents = _open_agents(self)
    if agents is None:
        _clear(self, "_decision_items", ids)
        self._decision_sig = None
        self._decision_hits = []
        return
    try:
        placed = place_open_decisions(agents, boxes, scale)
    except Exception:
        logging.getLogger("cli_avatars.decisions").exception("decision bubble failed")
        _clear(self, "_decision_items", ids)
        self._decision_sig = None
        self._decision_hits = []
        return
    self._decision_hits = [(x, y, w, h) for _agent_id, x, y, w, h in placed]
    if not placed:
        _clear(self, "_decision_items", ids)
        self._decision_sig = ()
        return
    key = ("decision", scale)
    sig = (key, tuple((x, y) for _agent_id, x, y, _w, _h in placed))
    if sig == getattr(self, "_decision_sig", None) and len(ids) == len(placed):
        return
    photo = photos_for(self).get(key, lambda scale=scale: render_bubble("decision", scale, 0, 1.0))
    if photo is None:
        _clear(self, "_decision_items", ids)
        self._decision_sig = None
        return
    rows = [(x, y, photo, "decision_bubble") for _agent_id, x, y, _w, _h in placed]
    self._decision_items = sync_images(self.canvas, ids, rows)
    self._decision_photo = photo
    self._decision_sig = sig


def _draw_blocked_marks(self: Any) -> None:
    """Amber '!' above an avatar whose state is blocked.

    The badge is a separate canvas image. It does not change the
    sprite cell (orchestrators stay 40×40, subagents 32×32).
    """
    ids = list(getattr(self, "_blocked_items", None) or [])
    if not _ready():
        _clear(self, "_blocked_items", ids)
        self._blocked_sig = None
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
        _clear(self, "_blocked_items", ids)
        self._blocked_sig = ()
        return
    spots = [place_blocked_mark(box, scale) for box in boxes]
    key = ("blocked", scale)
    sig = (key, tuple((x, y) for x, y, _w, _h in spots))
    if sig == getattr(self, "_blocked_sig", None) and len(ids) == len(spots):
        return
    photo = photos_for(self).get(key, lambda scale=scale: blocked_indicator(scale))
    if photo is None:
        _clear(self, "_blocked_items", ids)
        self._blocked_sig = None
        return
    rows = [(x, y, photo, "blocked_mark") for x, y, _w, _h in spots]
    self._blocked_items = sync_images(self.canvas, ids, rows)
    self._blocked_photo = photo
    self._blocked_sig = sig


class BubblesView:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.activity = ActivityDraw()
        bus = getattr(getattr(app, "scanner", None), "bus", None)
        if bus is not None:
            bus.subscribe(recap.TALLY.on_event)

    def step(self, frame: Any = None) -> None:
        now = getattr(frame, "now", None) if frame is not None else None
        _draw_talk_bubbles(self.app, now)
        focus_mode.step(self.app)
        decide_watch.step(self.app)
        needs_panel.step(self.app)
        recap_panel.step(self.app)
        mail_panel.step(self.app)
        standup_panel.step(self.app)
        _draw_decision_bubbles(self.app)
        _draw_blocked_marks(self.app)
        if now is None:
            now = time.time()
        self.activity.step(self.app, now)
