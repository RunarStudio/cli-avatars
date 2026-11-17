"""
perchas.py: window-top perches for the avatars.

Pure Python, no Win32 calls, so it is fully unit-testable.
See WINDOW-PERCHES-PLAN.md.

Input: windows in z-order, topmost first. Any object with
  .hwnd: int
  .rect: (left, top, right, bottom)   visible frame, right/bottom exclusive
  .maximized: bool
works (win32.Win, or a fake in tests).

A perch is one visible piece of a window's top edge: the edge minus the parts
covered by windows higher in z-order. Maximized windows give no perch but still
cover the windows below them. (Minimized windows never reach this module:
win32.list_windows drops them first.)
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

Interval = tuple[int, int]          # half-open [a, b)
Rect = tuple[int, int, int, int]    # left, top, right, bottom


@dataclass(frozen=True)
class Perch:
    hwnd: int
    x1: int
    x2: int
    y: int

    @property
    def length(self) -> int:
        return self.x2 - self.x1


def subtract(seg: Interval, cuts: Iterable[Interval]) -> list[Interval]:
    """Return the parts of `seg` not covered by any cut. All intervals are [a, b)."""
    a, b = seg
    if b <= a:
        return []
    out: list[Interval] = []
    cur = a
    for c1, c2 in sorted(cuts):
        if c2 <= cur or c1 >= c2:
            continue                 # behind us, or empty cut
        if c1 >= b:
            break                    # past the end of the segment
        if c1 > cur:
            out.append((cur, c1))
        cur = max(cur, c2)
        if cur >= b:
            return out
    if cur < b:
        out.append((cur, b))
    return out


def _covers_row(r: Rect, y: int, headroom: int) -> bool:
    """True if rect r hides row y, or the `headroom` px just above it."""
    _, top, _, bottom = r
    return top <= y and bottom > y - headroom


def build_perches(wins: Sequence, screen: Rect,
                  min_len: int = 40, headroom: int = 0) -> list[Perch]:
    """Visible top-edge segments of every non-maximized window."""
    sl, st, sr, sb = screen
    perches: list[Perch] = []
    for i, w in enumerate(wins):
        if w.maximized:
            continue
        left, top, right, _ = w.rect
        if not (st <= top < sb):
            continue                 # edge is off screen
        edge = (max(left, sl), min(right, sr))
        cuts = [(h.rect[0], h.rect[2]) for h in wins[:i]
                if _covers_row(h.rect, top, headroom)]
        for x1, x2 in subtract(edge, cuts):
            if x2 - x1 >= min_len:
                perches.append(Perch(w.hwnd, x1, x2, top))
    return perches


def build_walls(wins: Sequence, screen: Rect,
                min_len: int = 40) -> list[tuple[int, int, int]]:
    """Visible side edges as (x, y1, y2), the format overlay.py uses today."""
    sl, st, sr, sb = screen
    walls: list[tuple[int, int, int]] = []
    for i, w in enumerate(wins):
        if w.maximized:
            continue
        left, top, right, bottom = w.rect
        span = (max(top, st), min(bottom, sb))
        # (wall x, pixel column that must be visible)
        for wx, col in ((left, left), (right, right - 1)):
            if not (sl <= col < sr):
                continue
            cuts = [(h.rect[1], h.rect[3]) for h in wins[:i]
                    if h.rect[0] <= col < h.rect[2]]
            for y1, y2 in subtract(span, cuts):
                if y2 - y1 >= min_len:
                    walls.append((wx, y1, y2))
    return walls


def window_moves(prev: dict[int, tuple[int, int]],
                 cur: dict[int, tuple[int, int]]) -> dict[int, tuple[int, int]]:
    """(dx, dy) for every window present in both snapshots that moved.

    Snapshots map hwnd -> (left, top). A window missing from `cur` (closed,
    minimized, maximized) gets no entry: the avatar on it just falls.
    """
    moves: dict[int, tuple[int, int]] = {}
    for hwnd, (x, y) in cur.items():
        old = prev.get(hwnd)
        if old is not None and (x, y) != old:
            moves[hwnd] = (x - old[0], y - old[1])
    return moves
