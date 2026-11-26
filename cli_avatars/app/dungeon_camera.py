"""NAV.1: the Dungeon floor's camera. Integer zoom 1-3 and a pan in canvas px, with short eased glides. No Tk.

The rooms image is drawn at ``scale`` with its centre at the canvas centre plus ``pan`` (``D = S * z + pan``).
``auto`` zoom is the fit scale and follows every resize. The pan is clamped so the canvas centre always lies
over the map's box: the map never leaves the view. Every floor layer reads the painter's centre and scale,
so drops, glow, plaques and hit-testing follow the camera.
"""

from __future__ import annotations

import time

from cli_avatars.app.dungeon_rooms import fit_scale

ZOOMS = (1, 2, 3)
EASE_S = 0.22
KEY_STEP = 48
WHEEL_UNIT = 120
_KEYS = {"w": (0, 1), "up": (0, 1), "s": (0, -1), "down": (0, -1),
         "a": (1, 0), "left": (1, 0), "d": (-1, 0), "right": (-1, 0)}


def key_pan(keysym: str) -> tuple[int, int] | None:
    """Pan for a WASD or arrow key: the view moves the way the key points, so the map moves the other way."""
    step = _KEYS.get(str(keysym).lower())
    return None if step is None else (step[0] * KEY_STEP, step[1] * KEY_STEP)


class Camera:
    """Zoom (``auto`` or 1-3) and pan; ``view`` turns them into the painter's scale and image centre."""

    def __init__(self, zoom: object = "auto", pan=(0, 0), clock=time.monotonic) -> None:
        self.zoom = zoom if zoom in ZOOMS and not isinstance(zoom, bool) else "auto"
        self.pan = _ints(pan)
        self.clock = clock
        self.size = (0, 0)
        self.box = (0, 0)
        self._ease = None
        self._wheel = 0

    def scale(self) -> int:
        return fit_scale(self.size, self.box) if self.zoom == "auto" else int(self.zoom)

    def view(self, size, box) -> tuple[int, tuple[int, int]]:
        """Scale and image centre for a ``box`` canvas over a ``size`` map; advances a glide, clamps the pan."""
        self.size, self.box = (int(size[0]), int(size[1])), (int(box[0]), int(box[1]))
        if self._ease is not None:
            t0, start, goal = self._ease
            k = min(1.0, max(0.0, (self.clock() - t0) / EASE_S))
            e = 1.0 - (1.0 - k) ** 3
            self.pan = (round(start[0] + (goal[0] - start[0]) * e), round(start[1] + (goal[1] - start[1]) * e))
            if k >= 1.0:
                self._ease = None
        s = self.scale()
        self.pan = self._clamp(self.pan, s)
        return s, (self.box[0] // 2 + self.pan[0], self.box[1] // 2 + self.pan[1])

    def moving(self) -> bool:
        return self._ease is not None

    def zoom_by(self, steps: int, at=None) -> bool:
        """``steps`` levels in (+) or out (-), keeping the floor point under canvas point ``at`` still."""
        s1 = self.scale()
        s2 = max(ZOOMS[0], min(ZOOMS[-1], s1 + int(steps)))
        if s2 == s1:
            return False
        self._ease = None
        ax, ay = (at[0] - self.box[0] // 2, at[1] - self.box[1] // 2) if at is not None else (0, 0)
        pan = (round(ax - (ax - self.pan[0]) * s2 / s1), round(ay - (ay - self.pan[1]) * s2 / s1))
        self.zoom = s2
        self.pan = self._clamp(pan, s2)
        return True

    def wheel(self, delta: int, at) -> bool:
        """A wheel turn: one zoom level per notch of 120 (touchpads send smaller deltas that add up)."""
        self._wheel += int(delta)
        steps = int(self._wheel / WHEEL_UNIT)
        if not steps:
            return False
        self._wheel -= steps * WHEEL_UNIT
        return self.zoom_by(steps, at)

    def move(self, dx: int, dy: int) -> bool:
        """Pan by canvas px (drag or key); the scale shown now is kept."""
        self._ease = None
        if self.zoom == "auto":
            self.zoom = self.scale()
        before = self.pan
        self.pan = self._clamp((self.pan[0] + int(dx), self.pan[1] + int(dy)), self.scale())
        return self.pan != before

    def glide(self, offset) -> None:
        """Ease so the point ``offset`` px from the image centre ends at the canvas centre."""
        if self.zoom == "auto":
            self.zoom = self.scale()
        self._ease = (self.clock(), self.pan, self._clamp((-round(offset[0]), -round(offset[1])), self.scale()))

    def jump(self, offset) -> None:
        """A room jump: from the whole map it zooms one level in around the room, then glides it to the centre."""
        s1 = self.scale()
        if self.zoom == "auto" and s1 < ZOOMS[-1]:
            self.zoom_by(1, (self.box[0] // 2 + self.pan[0] + offset[0], self.box[1] // 2 + self.pan[1] + offset[1]))
        s2 = self.scale()
        self.glide((offset[0] * s2 / s1, offset[1] * s2 / s1))

    def home(self) -> None:
        """The whole map: fit zoom, glide back to the centre."""
        s1 = self.scale()
        self.zoom = "auto"
        s2 = self.scale()
        self.pan = (round(self.pan[0] * s2 / s1), round(self.pan[1] * s2 / s1))
        self._ease = (self.clock(), self.pan, (0, 0))

    def hold(self, before, after) -> None:
        """The map image changed from ``before`` to ``after`` ``(left, top, w, h)`` (a room grew or went): when zoomed
        in, shift the pan so the floor under the view stays put; the whole-map view just fits again."""
        if self.zoom == "auto" or before is None or after is None or self._ease is not None:
            return
        s = self.scale()
        self.pan = (round(self.pan[0] + (after[2] - before[2]) * s / 2 + (after[0] - before[0]) * s),
                    round(self.pan[1] + (after[3] - before[3]) * s / 2 + (after[1] - before[1]) * s))

    def saved(self) -> tuple[object, tuple[int, int]]:
        """Zoom and pan to store: where a running glide ends."""
        return self.zoom, (self._ease[2] if self._ease is not None else self.pan)

    def _clamp(self, pan, s: int) -> tuple[int, int]:
        hx, hy = self.size[0] * s // 2, self.size[1] * s // 2
        if hx <= 0 or hy <= 0:
            return _ints(pan)
        return (max(-hx, min(hx, int(pan[0]))), max(-hy, min(hy, int(pan[1]))))


def _ints(pan) -> tuple[int, int]:
    try:
        return int(pan[0]), int(pan[1])
    except (TypeError, ValueError, IndexError):
        return 0, 0
