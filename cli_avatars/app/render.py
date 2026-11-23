"""Floor lines, elastic lines, and the burst / glitch pass.

BLDG.2: ``building_window.Toplevel`` should take a ``PhotoCache``.
SPLIT.5 moves PhotoImage creation into that cache. Until then each call
site still builds its own image and keeps it on the shell.
"""

import math

from cli_avatars.effects.burst import BurstEffect
from cli_avatars.model.agent import AGENT_STATUS_COLOR as STATUS_COLOR
from cli_avatars.physics.geometry import child_flight_mode, elastic_endpoints
from cli_avatars.tuning import FLOOR_LINE_COLOR, TUNING
from cli_avatars.world.avatar import Avatar


def _alpha_stipple(alpha: float) -> str:
    """Map 0–1 opacity to a tkinter canvas stipple pattern string."""
    if alpha >= 1.0:  return ""
    if alpha >= 0.75: return "gray75"
    if alpha >= 0.5:  return "gray50"
    if alpha >= 0.25: return "gray25"
    return "gray12"


def _draw_elastic(self, parent_av: Avatar, sv: Avatar, shrink: float = 1.0):
    """Draw a purple zigzag spring line between parent and subagent.

    Ground children keep the line from centre to centre. Fly children
    start at the parent's head so the line is drawn upward.
    ``shrink`` pulls the parent end toward the child while a child
    is dying (1 is the full line, 0 draws nothing).
    """
    if not math.isfinite(shrink):
        shrink = 1.0
    shrink = max(0.0, min(1.0, float(shrink)))
    if shrink <= 0.05:
        return
    x0, y0, x1, y1 = elastic_endpoints(parent_av, sv, child_flight_mode(sv))
    x0 = x1 + (x0 - x1) * shrink
    y0 = y1 + (y0 - y1) * shrink
    dx, dy = x1 - x0, y1 - y0
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < 4:
        return
    # Perpendicular unit vector for zigzag offset
    px_v = -dy / dist;  py_v = dx / dist
    SEGS = 10
    amp  = min(8.0, dist * 0.08)
    pts  = []
    for i in range(SEGS + 1):
        t  = i / SEGS
        mx = x0 + dx * t;  my = y0 + dy * t
        if i == 0 or i == SEGS:
            pts.append((mx, my))
        else:
            sign = 1 if i%2 else -1
            pts.append((mx + px_v*amp*sign, my + py_v*amp*sign))
    for i in range(len(pts)-1):
        self.canvas.create_line(
            pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
            fill="#aa44ff", width=1, tags="elastic")


def floor_lines(self, frame):
    """Delete elastic and floor marks, then redraw the floor marks.

    Elastic lines are cleared here, before subagents draw them again.
    """
    floors = frame.floors
    walls = frame.walls
    self.canvas.delete("elastic")   # clear all elastic lines
    self.canvas.delete("floor_line")
    if TUNING.floor_line_alpha > 0:
        stpl = _alpha_stipple(TUNING.floor_line_alpha)
        for (fx1, fy, fx2, _) in floors:
            # Inset 16px from each end so floor doesn't touch wall corners
            self.canvas.create_line(fx1 + 16, fy, fx2 - 16, fy,
                                    fill=FLOOR_LINE_COLOR, width=2,
                                    stipple=stpl, tags="floor_line")
        for (wx, wy1, wy2) in walls:
            # Start 24px below window top so wall clears the floor line
            self.canvas.create_line(wx, wy1 + 24, wx, wy2,
                                    fill=FLOOR_LINE_COLOR, width=1,
                                    stipple=stpl, tags="floor_line")


def effects(self, frame=None):
    for av in list(self.avatars.values()):
        if av._burst_requested:
            av._burst_requested = False
            self._bursts.append(BurstEffect(
                av.x + av.aw / 2, av.y - 10,
                STATUS_COLOR.get(av.agent.status, "#44ff88")))

    self._bursts   = [b for b in self._bursts   if b.tick(self.canvas)]
    self._glitches = [g for g in self._glitches if g.tick()]


def color_for(av):
    return STATUS_COLOR.get(av.agent.status, av.color)


class PhotoCache:
    """One PhotoImage per key. SPLIT.5 fills the tick in.

    BLDG.2's building window should use this. Nothing in the frame calls
    it yet, so sprite lifetime on the overlay is unchanged.
    """

    def __init__(self):
        self._photos = {}

    def get(self, key, factory):
        photo = self._photos.get(key)
        if photo is None:
            photo = factory()
            if photo is not None:
                self._photos[key] = photo
        return photo


class RenderController:
    def __init__(self, app):
        self.app = app
        self.photos = PhotoCache()

    def floor_lines(self, frame):
        return floor_lines(self.app, frame)

    def effects(self, frame=None):
        return effects(self.app, frame)

    def draw_elastic(self, parent_av, sv, shrink=1.0):
        return _draw_elastic(self.app, parent_av, sv, shrink)

    def color_for(self, av):
        return color_for(av)
