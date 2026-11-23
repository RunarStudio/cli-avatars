"""One portal on the meeting surface, behind the avatars."""

import logging
import time
from typing import Any

from bubbles import integer_scale
from cli_avatars.app.render import photos_for, sync_images
from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.tuning import TUNING
from portal import portal_top_left, render_portal

if HAS_PIL:
    try:
        from PIL import ImageTk as _ImageTk
    except ImportError:
        HAS_PIL = False
        _ImageTk = None
else:
    _ImageTk = None


def _draw_portal(self: Any, floors, floor_hwnds) -> None:
    """One portal on the meeting surface, behind the avatars."""
    ids = list(getattr(self, "_portal_items", None) or [])
    if not HAS_PIL or _ImageTk is None:
        self._portal_items = sync_images(self.canvas, ids, [])
        self._portal_sig = None
        return
    try:
        stage = self._meeting_stage(floors, floor_hwnds)
        view = self._portal.advance(self.scanner.meetings.mark(stage), time.time())
    except Exception:
        logging.getLogger("cli_avatars.portal").exception("portal draw failed")
        self._portal_items = sync_images(self.canvas, ids, [])
        self._portal_sig = None
        return
    if view is None:
        self._portal_items = sync_images(self.canvas, ids, [])
        self._portal_sig = None
        return
    scale = integer_scale(TUNING.avatar_scale)
    key = ("portal", view.phase, view.index, scale)
    x, y = portal_top_left(view.surface_x, view.surface_y, scale)
    x, y = int(round(x)), int(round(y))
    sig = (key, x, y)
    if sig == getattr(self, "_portal_sig", None) and ids:
        self.canvas.tag_lower("portal")
        if self.canvas.find_withtag("floor_line"):
            self.canvas.tag_raise("portal", "floor_line")
        return
    photo = photos_for(self).get(key, lambda spec=view.spec, scale=scale: render_portal(spec, scale, 1))
    if photo is None:
        self._portal_items = sync_images(self.canvas, ids, [])
        self._portal_sig = None
        return
    self._portal_items = sync_images(self.canvas, ids, [(x, y, photo, "portal")])
    self._portal_sig = sig
    self.canvas.tag_lower("portal")
    if self.canvas.find_withtag("floor_line"):
        self.canvas.tag_raise("portal", "floor_line")


class PortalView:
    def __init__(self, app: Any) -> None:
        self.app = app

    def step(self, frame: Any) -> None:
        return _draw_portal(self.app, frame.floors, frame.floor_hwnds)
