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

    def _apply(self, snapshot):
        floors, walls, hwnds, pos = snapshot
        with self._lock:
            self._floors      = floors
            self._walls       = walls
            self._floor_hwnds = hwnds
            self._win_pos     = pos

    def _scan(self):
        if self._list_windows is not None:
            try:
                wins = self._list_windows()
                if not self._screen:
                    return
                snapshot = terrain_from_windows(wins, self._screen)
            except Exception as e:
                print(f"[WARN] Terrain (win32): {e}")
                return
            self._apply(snapshot)
            return
        snapshot = scan_live(self._own, self._screen)
        if snapshot is None:
            return
        self._apply(snapshot)

    def get_snapshot(self) -> tuple:
        """(floors, walls, floor_hwnds, window positions), all from the same scan."""
        with self._lock:
            return (list(self._floors), list(self._walls),
                    list(self._floor_hwnds), dict(self._win_pos))

    def loop(self) -> None:
        n, times = 0, []
        while True:
            t0 = time.perf_counter()
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
