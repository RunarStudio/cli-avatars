"""One portal on the meeting surface, behind the avatars."""

import logging
import time

from bubbles import integer_scale
from portal import portal_top_left, render_portal

from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.tuning import TUNING

if HAS_PIL:
    try:
        from PIL import ImageTk
    except ImportError:
        HAS_PIL = False


def _draw_portal(self, floors, floor_hwnds):
    """One portal on the meeting surface, behind the avatars."""
    self.canvas.delete("portal")
    if not HAS_PIL:
        return
    try:
        stage = self._meeting_stage(floors, floor_hwnds)
        view = self._portal.advance(self.scanner.meetings.mark(stage), time.time())
    except Exception:
        logging.getLogger("cli_avatars.portal").exception("portal draw failed")
        return
    if view is None:
        return
    scale = integer_scale(TUNING.avatar_scale)
    key = (view.phase, view.index, scale)
    photo = self._portal_cache.get(key)
    if photo is None:
        image = render_portal(view.spec, scale, 1)
        photo = ImageTk.PhotoImage(image)
        self._portal_cache[key] = photo
    x, y = portal_top_left(view.surface_x, view.surface_y, scale)
    self.canvas.create_image(int(round(x)), int(round(y)), image=photo, anchor="nw", tags="portal")
    self.canvas.tag_lower("portal")
    if self.canvas.find_withtag("floor_line"):
        self.canvas.tag_raise("portal", "floor_line")


class PortalView:
    def __init__(self, app):
        self.app = app

    def step(self, frame):
        return _draw_portal(self.app, frame.floors, frame.floor_hwnds)
