"""LAYOUT.1: the splitters between the map and the side columns: drag, collapse to the edge, double-click resets.

A column's width is the pointer's distance from the window body's own edge, so the right column follows the
pointer too. It used to be measured from the column's left edge, which lies right of its splitter: every drag
clamped it to its minimum and it stayed there. The widths Daniel picks are kept apart from the shown ones: a
narrow window shrinks the columns so the map keeps room, a wide one gives the picked widths back.
``ui/dungeon_window.json`` stores the picked widths.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.dungeon_geom import DEFAULT_LEFT, DEFAULT_RIGHT, SCENE_MIN, fit_dock_widths

SASH_W = 6
LIMITS = {"left": (160, 640), "right": (200, 720)}
DEFAULTS = {"left": DEFAULT_LEFT, "right": DEFAULT_RIGHT}
COLLAPSE = 0.5
SCENE_SHARE = 0.4
_EDGE, _GRIP, _LIT = "#2a2436", "#6a5432", "#ffcf4a"


def prefs(view) -> dict:
    """The widths Daniel picked, per side."""
    found = getattr(view, "_dock_pref", None)
    if not isinstance(found, dict):
        found = view._dock_pref = dict(DEFAULTS)
    return found


def drag(view, frame, event, low: int, high: int) -> None:
    """Width from the body edge; under half the minimum the column collapses to its edge."""
    side = "right" if frame is view._right else "left"
    body = frame.master
    edge = int(body.winfo_rootx())
    width = int(event.x_root) - edge if side == "left" else edge + int(body.winfo_width()) - int(event.x_root)
    if width < low * COLLAPSE:
        if _is_open(view, side):
            _open(view, side, False)
        return
    other = view._left if side == "right" else view._right
    used = int(other.winfo_width()) if _is_open(view, "left" if side == "right" else "right") else 0
    room = int(body.winfo_width()) - used - 2 * SASH_W - SCENE_MIN
    width = max(low, min(high, room, width))
    prefs(view)[side] = width
    frame.configure(width=width)
    if not _is_open(view, side):
        _open(view, side, True)
    view._schedule_save()


def reset(view, side: str) -> None:
    """Double-click on a splitter: the default width, column open."""
    prefs(view)[side] = DEFAULTS[side]
    if _is_open(view, side):
        reflow(view)
    else:
        _open(view, side, True)
    view._schedule_save()


def reflow(view) -> None:
    """Shown widths for the body's width now: the picked ones, shrunk while the map would get too little."""
    try:
        body_w = int(view._mid.master.winfo_width())
    except (tk.TclError, AttributeError):
        return
    if body_w < 2:
        return
    left_open, right_open = bool(getattr(view.app, "_rooms_shown", True)), bool(getattr(view, "_right_open", True))
    want = prefs(view)
    scene_min = max(SCENE_MIN, int(body_w * SCENE_SHARE))
    left, right = fit_dock_widths(body_w - 2 * SASH_W, want["left"], want["right"], left_open, right_open, scene_min)
    for frame, width in ((view._left, left), (view._right, right)):
        if int(frame.cget("width")) != width:
            frame.configure(width=width)


def make(view, body, side: str):
    """One splitter: a thin stone edge with an ember grip, drawn in code."""
    sash = tk.Canvas(body, width=SASH_W, bg=_EDGE, highlightthickness=0, bd=0, cursor="sb_h_double_arrow")
    frame = view._left if side == "left" else view._right
    low, high = LIMITS[side]
    sash.bind("<B1-Motion>", lambda e: view.drag_dock(frame, e, low, high))
    sash.bind("<Double-Button-1>", lambda _e: reset(view, side))
    sash.bind("<Configure>", lambda e: _grip(sash, e.height, _GRIP))
    sash.bind("<Enter>", lambda _e: _grip(sash, sash.winfo_height(), _LIT))
    sash.bind("<Leave>", lambda _e: _grip(sash, sash.winfo_height(), _GRIP))
    return sash


def _grip(sash, height: int, color: str) -> None:
    sash.delete("grip")
    mid = int(height) // 2
    for n in range(-3, 4):
        y = mid + n * 5
        sash.create_rectangle(2, y, 4, y + 2, fill=color, outline="", tags="grip")


def _is_open(view, side: str) -> bool:
    if side == "left":
        return bool(getattr(view.app, "_rooms_shown", True))
    return bool(getattr(view, "_right_open", True))


def _open(view, side: str, open_: bool) -> None:
    if side == "left":
        view.set_left(open_)
    else:
        view.set_right(open_)
