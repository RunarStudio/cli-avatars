"""Floor lines, elastic lines, PhotoCache, and the burst / glitch pass.

One ``ImageTk.PhotoImage`` is kept per (sheet, row, frame, mirror, hue, scale).
Floor lines, elastic segments, the portal, and bubbles keep their canvas ids
and move with ``coords`` / ``itemconfig``. An unchanged signature is not redrawn.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from cli_avatars.effects.burst import BurstEffect
from cli_avatars.model.agent import AGENT_STATUS_COLOR as STATUS_COLOR
from cli_avatars.physics.geometry import child_flight_mode, elastic_endpoints
from cli_avatars.tuning import FLOOR_LINE_COLOR, TUNING
from cli_avatars.world.avatar import Avatar

_ELASTIC_SEGS = 10


def _alpha_stipple(alpha: float) -> str:
    """Map 0–1 opacity to a tkinter canvas stipple pattern string."""
    if alpha >= 1.0:
        return ""
    if alpha >= 0.75:
        return "gray75"
    if alpha >= 0.5:
        return "gray50"
    if alpha >= 0.25:
        return "gray25"
    return "gray12"


def _to_photo(image: object) -> object | None:
    """Wrap a PIL image once. A PhotoImage or a test sentinel is kept as-is."""
    if image is None:
        return None
    try:
        from PIL import Image
    except ImportError:
        return image
    if not isinstance(image, Image.Image):
        return image
    try:
        from PIL import ImageTk
    except ImportError:
        return None
    return ImageTk.PhotoImage(image)


class PhotoCache:
    """One PhotoImage per key. Entries are not evicted.

    The key is ``(sheet, row, frame, mirror, hue, scale)`` for a sheet, and
    the procedural equivalent (body color, status, walk frame, bob, mirror,
    hue, scale). The same key returns the same object.
    """

    def __init__(self) -> None:
        self._photos: dict[tuple, object] = {}

    def __len__(self) -> int:
        return len(self._photos)

    def get(self, key: tuple, factory: Callable[[], object | None]) -> object | None:
        cached = self._photos.get(key)
        if cached is not None:
            return cached
        made = factory()
        if made is None:
            return None
        photo = _to_photo(made)
        if photo is None:
            return None
        self._photos[key] = photo
        return photo


def canvas_photos(app: object) -> PhotoCache | None:
    """The shell cache, when the render controller has been built."""
    render = getattr(app, "render", None)
    photos = getattr(render, "photos", None) if render is not None else None
    if isinstance(photos, PhotoCache):
        return photos
    return None


def photos_for(app: object) -> PhotoCache:
    """Cache for this shell. A bare app object gets one on first use."""
    found = canvas_photos(app)
    if found is not None:
        return found
    cache = getattr(app, "_photo_cache", None)
    if not isinstance(cache, PhotoCache):
        cache = PhotoCache()
        app._photo_cache = cache
    return cache


def sync_images(canvas: Any, ids: list, placed: list[tuple]) -> list:
    """Move or create canvas images. ``placed`` is ``(x, y, photo, tag)``."""
    while len(ids) > len(placed):
        canvas.delete(ids.pop())
    for index, (x, y, photo, tag) in enumerate(placed):
        if index < len(ids):
            canvas.coords(ids[index], x, y)
            canvas.itemconfig(ids[index], image=photo)
        else:
            ids.append(canvas.create_image(x, y, image=photo, anchor="nw", tags=tag))
    return ids


def _floor_spec(frame: Any) -> tuple:
    alpha = TUNING.floor_line_alpha
    stipple = _alpha_stipple(alpha)
    lines: list[tuple] = []
    if alpha > 0:
        for (fx1, fy, fx2, _) in frame.floors:
            lines.append((fx1 + 16, fy, fx2 - 16, fy, 2, stipple, FLOOR_LINE_COLOR))
        for (wx, wy1, wy2) in frame.walls:
            lines.append((wx, wy1 + 24, wx, wy2, 1, stipple, FLOOR_LINE_COLOR))
    return tuple(lines)


def _sync_lines(canvas: Any, ids: list, spec: tuple) -> list:
    ids = list(ids)
    while len(ids) > len(spec):
        canvas.delete(ids.pop())
    for index, (x0, y0, x1, y1, width, stipple, color) in enumerate(spec):
        if index < len(ids):
            canvas.coords(ids[index], x0, y0, x1, y1)
            canvas.itemconfig(ids[index], fill=color, width=width, stipple=stipple)
        else:
            ids.append(canvas.create_line(
                x0, y0, x1, y1,
                fill=color, width=width, stipple=stipple, tags="floor_line",
            ))
    return ids


def _line_hits(x0: float, y0: float, x1: float, y1: float, rect: tuple) -> bool:
    left, top, right, bottom = rect
    return not (
        max(x0, x1) < left or min(x0, x1) > right
        or max(y0, y1) < top or min(y0, y1) > bottom
    )


def _clear_ids(canvas: Any, ids: list) -> None:
    for iid in ids:
        try:
            canvas.delete(iid)
        except Exception:
            return


def floor_lines(self: Any, frame: Any) -> None:
    """Redraw floor and wall marks only when their geometry or alpha changed.

    Elastic segments are owned by each child and are not cleared here.
    With one overlay per monitor, a mark is painted on each canvas it
    crosses, in that monitor's local pixels.
    """
    spec = _floor_spec(frame)
    board = getattr(self, "overlays", None)
    slots = []
    if board is not None and not getattr(board, "legacy", True):
        slots = list(board.slots())
    if not slots:
        for stored in (getattr(self, "_floor_boards", None) or {}).values():
            _clear_ids(stored[2], stored[1])
        self._floor_boards = {}
        if spec == getattr(self, "_floor_spec", None) and getattr(self, "_floor_ids", None) is not None:
            return
        self._floor_ids = _sync_lines(self.canvas, getattr(self, "_floor_ids", None) or [], spec)
        self._floor_spec = spec
        return
    _clear_ids(self.canvas, list(getattr(self, "_floor_ids", None) or []))
    self._floor_ids = None
    self._floor_spec = None
    boards = getattr(self, "_floor_boards", None)
    if not isinstance(boards, dict):
        boards = {}
        self._floor_boards = boards
    live = set()
    for slot in slots:
        live.add(slot.key)
        ox, oy = slot.origin
        local = tuple(
            (x0 - ox, y0 - oy, x1 - ox, y1 - oy, width, stipple, color)
            for (x0, y0, x1, y1, width, stipple, color) in spec
            if _line_hits(x0, y0, x1, y1, slot.monitor.rect)
        )
        prev = boards.get(slot.key)
        if prev is not None and prev[0] == local:
            continue
        ids = _sync_lines(slot.canvas, [] if prev is None else prev[1], local)
        boards[slot.key] = (local, ids, slot.canvas)
    for key in list(boards):
        if key not in live:
            _old, ids, canvas = boards.pop(key)
            _clear_ids(canvas, ids)


def _clear_elastic(canvas: Any, sv: Avatar) -> None:
    for iid in getattr(sv, "_elastic_ids", None) or []:
        canvas.delete(iid)
    sv._elastic_ids = []
    sv._elastic_sig = None


def _elastic_points(parent_av: Avatar, sv: Avatar, shrink: float) -> list[tuple[float, float]] | None:
    if not math.isfinite(shrink):
        shrink = 1.0
    shrink = max(0.0, min(1.0, float(shrink)))
    if shrink <= 0.05:
        return None
    x0, y0, x1, y1 = elastic_endpoints(parent_av, sv, child_flight_mode(sv))
    x0 = x1 + (x0 - x1) * shrink
    y0 = y1 + (y0 - y1) * shrink
    dx, dy = x1 - x0, y1 - y0
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 4:
        return None
    px_v = -dy / dist
    py_v = dx / dist
    amp = min(8.0, dist * 0.08)
    pts: list[tuple[float, float]] = []
    for i in range(_ELASTIC_SEGS + 1):
        t = i / _ELASTIC_SEGS
        mx = x0 + dx * t
        my = y0 + dy * t
        if i == 0 or i == _ELASTIC_SEGS:
            pts.append((mx, my))
        else:
            sign = 1 if i % 2 else -1
            pts.append((mx + px_v * amp * sign, my + py_v * amp * sign))
    return pts


def _draw_elastic(self: Any, parent_av: Avatar, sv: Avatar, shrink: float = 1.0) -> None:
    """Keep the purple zigzag and move it when the pair moves.

    Ground children keep the line from centre to centre. Fly children
    start at the parent's head so the line is drawn upward.
    ``shrink`` pulls the parent end toward the child while a child
    is dying (1 is the full line, 0 draws nothing).
    """
    ids = list(getattr(sv, "_elastic_ids", None) or [])
    pts = _elastic_points(parent_av, sv, shrink)
    if not pts:
        _clear_elastic(self.canvas, sv)
        return
    sig = tuple(pts)
    if sig == getattr(sv, "_elastic_sig", None) and len(ids) == len(pts) - 1:
        return
    need = len(pts) - 1
    while len(ids) > need:
        self.canvas.delete(ids.pop())
    for i in range(need):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if i < len(ids):
            self.canvas.coords(ids[i], x0, y0, x1, y1)
        else:
            ids.append(self.canvas.create_line(
                x0, y0, x1, y1, fill="#aa44ff", width=1, tags="elastic",
            ))
    sv._elastic_ids = ids
    sv._elastic_sig = sig


def effects(self: Any, frame: Any = None) -> None:
    for av in list(self.avatars.values()):
        if av._burst_requested:
            av._burst_requested = False
            self._bursts.append(BurstEffect(
                av.x + av.aw / 2, av.y - 10,
                STATUS_COLOR.get(av.agent.status, "#44ff88")))

    self._bursts = [b for b in self._bursts if b.tick(self.canvas)]
    self._glitches = [g for g in self._glitches if g.tick()]


def color_for(av: Avatar) -> str:
    return STATUS_COLOR.get(av.agent.status, av.color)


class RenderController:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.photos = PhotoCache()

    def floor_lines(self, frame: Any) -> None:
        return floor_lines(self.app, frame)

    def effects(self, frame: Any = None) -> None:
        return effects(self.app, frame)

    def draw_elastic(self, parent_av: Avatar, sv: Avatar, shrink: float = 1.0) -> None:
        return _draw_elastic(self.app, parent_av, sv, shrink)

    def color_for(self, av: Avatar) -> str:
        return color_for(av)
