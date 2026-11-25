"""Floors and walls from the desktop window list.

Pass ``list_windows`` to use a fake list. The scan thread is started by
the overlay. This module does not start one and does not import tkinter.
"""

import threading
import time

from cli_avatars.desktop.capabilities import HAS_W32
from cli_avatars.desktop.windows import scan_live, terrain_from_windows
from cli_avatars.tuning import TUNING


class WindowTerrain:
    def __init__(self, own_title, screen=None, list_windows=None):
        self._floors: list[tuple] = []
        self._walls:  list[tuple] = []
        self._lock   = threading.Lock()
        self._own    = own_title
        self._screen = screen     # (left, top, right, bottom) of the overlay
        self._floor_hwnds: list[int] = []          # window of each floor (win32 path)
        self._win_pos: dict[int, tuple] = {}       # hwnd -> (left, top)
        self._list_windows = list_windows
        self._clip: list = []
        self._found: list = []
        self._mon_sig: str | None = None
        self._mon_dirty = False
        self._poll_s = 1.0
        self._next_poll = 0.0

    def _apply(self, snapshot):
        floors, walls, hwnds, pos = snapshot
        with self._lock:
            self._floors      = floors
            self._walls       = walls
            self._floor_hwnds = hwnds
            self._win_pos     = pos

    def set_world(self, screen, monitors) -> None:
        """Bounds the perch scan uses, and the monitors dead-zone pieces are cut against."""
        with self._lock:
            if screen:
                self._screen = screen
            self._clip = list(monitors or [])

    def note_monitors(self, found, poll_s: float) -> None:
        """Remember the list the shell already applied, and the poll interval."""
        from cli_avatars.desktop.monitors import monitor_signature

        with self._lock:
            self._found = list(found or [])
            self._mon_sig = monitor_signature(self._found)
            self._mon_dirty = False
            try:
                self._poll_s = float(poll_s)
            except (TypeError, ValueError):
                self._poll_s = 1.0

    def take_monitors(self) -> tuple:
        """``(changed, monitors, signature)``. The changed flag clears on read."""
        with self._lock:
            changed = self._mon_dirty
            self._mon_dirty = False
            return changed, list(self._found), self._mon_sig

    def _world(self) -> tuple:
        with self._lock:
            return self._screen, list(self._clip)

    def _poll_monitors(self) -> None:
        """Signature every ``monitor_poll_s``. Tk is not touched from this thread."""
        now = time.monotonic()
        if now < self._next_poll:
            return
        with self._lock:
            interval = self._poll_s if self._poll_s > 0 else 1.0
        self._next_poll = now + interval
        try:
            from cli_avatars.desktop.monitors import list_monitors, monitor_signature

            found = list_monitors()
            sig = monitor_signature(found)
        except Exception as exc:
            print(f"[WARN] Monitors: {exc}")
            return
        with self._lock:
            if self._mon_sig is None:
                self._mon_sig = sig
                self._found = list(found)
                return
            if sig != self._mon_sig:
                self._mon_sig = sig
                self._found = list(found)
                self._mon_dirty = True

    def _scan(self):
        screen, monitors = self._world()
        if self._list_windows is not None:
            try:
                wins = self._list_windows()
                if not screen:
                    return
                snapshot = terrain_from_windows(wins, screen, monitors)
            except Exception as e:
                print(f"[WARN] Terrain (win32): {e}")
                return
            self._apply(_clip_snapshot(snapshot, monitors))
            return
        snapshot = scan_live(self._own, screen, monitors)
        if snapshot is None:
            return
        self._apply(_clip_snapshot(snapshot, monitors))

    def get_snapshot(self) -> tuple:
        """(floors, walls, floor_hwnds, window positions), all from the same scan."""
        with self._lock:
            return (list(self._floors), list(self._walls),
                    list(self._floor_hwnds), dict(self._win_pos))

    def loop(self) -> None:
        n, times = 0, []
        while True:
            t0 = time.perf_counter()
            self._poll_monitors()
            self._scan()
            n += 1
            if 20 < n <= 40:               # skip startup (sprite loading), then log once
                times.append((time.perf_counter() - t0) * 1000)
                if n == 40:
                    times.sort()
                    print(f"[INFO] Terrain scan: median {times[10]:.2f} ms, min {times[0]:.2f}, "
                          f"max {times[-1]:.2f} ({'win32' if HAS_W32 else 'pywinctl'}), "
                          f"every {TUNING.window_scan_rate}s")
            time.sleep(TUNING.window_scan_rate)


class _Seg:
    """Perch stand-in. ``clip_perches`` rebuilds with ``type(perch)(hwnd, x1, x2, y)``."""

    def __init__(self, hwnd, x1, x2, y):
        self.hwnd = hwnd
        self.x1 = x1
        self.x2 = x2
        self.y = y


def _clip_snapshot(snapshot, monitors):
    """Drop perch and wall pieces that lie over a dead zone. No monitors means no cut."""
    if not monitors:
        return snapshot
    from cli_avatars.tuning import FLOOR_MARGIN
    from cli_avatars.world.monitors import clip_perches

    floors, walls, hwnds, pos = snapshot
    perches = []
    for index, floor in enumerate(floors):
        x1, y, x2, _margin = floor
        hwnd = hwnds[index] if index < len(hwnds) else 0
        perches.append(_Seg(hwnd, x1, x2, y))
    clipped = clip_perches(perches, monitors)
    new_floors = [(p.x1, p.y, p.x2, p.y + FLOOR_MARGIN) for p in clipped]
    new_hwnds = [p.hwnd for p in clipped]
    new_walls = [wall for wall in walls if _wall_hits(monitors, wall)]
    return new_floors, new_walls, new_hwnds, pos


def _wall_hits(monitors, wall) -> bool:
    wx, y1, y2 = wall
    for monitor in monitors:
        left, top, right, bottom = monitor.rect
        if left <= wx <= right and y2 >= top and y1 <= bottom:
            return True
    return False
