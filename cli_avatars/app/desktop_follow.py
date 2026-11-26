"""Click-through and Dungeon text scale. A shell timer, not the tick.

Windows only. Linux keeps the overlay withdrawn and does not start this.
"""

from __future__ import annotations

from cli_avatars.desktop.clickthrough import (
    cursor_point,
    overlay_pass_through,
    set_pass_through,
    top_hwnd,
)
from cli_avatars.desktop.dpi import read_window_dpi, set_dpi_aware
from cli_avatars.world.monitors import tk_scaling, ui_should_scale


def start(app) -> None:
    """Begin the 33 ms follow. No-op where the desktop overlay is off."""
    if not getattr(app, "desktop_escape", False):
        return

    def step() -> None:
        try:
            follow(app)
        except Exception:
            pass
        try:
            app.root.after(33, step)
        except Exception:
            return

    try:
        follow(app)
        app.root.after(33, step)
    except Exception:
        return


def follow(app) -> None:
    """One sample: text scale if the window DPI changed, then click-through."""
    _scale(app)
    if getattr(app, "_drag_av", None) is not None:
        return
    _clicks(app)


def hit_boxes(app) -> list[tuple[float, float, float, float]]:
    """Avatar, label, bubble, and portal boxes in virtual px. Empty space is not a box."""
    boxes = []
    for av in _bodies(app):
        width = float(getattr(av, "aw", 0) or 0)
        height = float(getattr(av, "ah", 0) or 0)
        if width <= 0 or height <= 0:
            continue
        boxes.append((float(av.x), float(av.y) - 20.0, width, height + 20.0))
    for extra in list(getattr(app, "_bubble_hits", ()) or ()):
        _take(boxes, extra)
    for extra in list(getattr(app, "_activity_hits", ()) or ()):
        _take(boxes, extra)
    for extra in list(getattr(app, "_decision_hits", ()) or ()):
        _take(boxes, extra)
    _take(boxes, getattr(app, "_portal_hit", None))
    return boxes


def _take(boxes, extra) -> None:
    if not extra or len(extra) < 4:
        return
    left, top, width, height = extra[:4]
    if float(width) <= 0 or float(height) <= 0:
        return
    boxes.append((float(left), float(top), float(width), float(height)))


def _clicks(app) -> None:
    board = getattr(app, "overlays", None)
    if board is None:
        return
    cursor = cursor_point()
    boxes = hit_boxes(app)
    cache = getattr(app, "_pass_cache", None)
    if cache is None:
        cache = {}
        app._pass_cache = cache
    for window, rect in _windows(board, app):
        hwnd = top_hwnd(window)
        if not hwnd:
            continue
        want = overlay_pass_through(cursor, rect, boxes)
        if cache.get(hwnd) is want:
            continue
        if set_pass_through(hwnd, want):
            cache[hwnd] = want


def _windows(board, app):
    if not getattr(board, "legacy", True):
        for slot in board.slots():
            yield slot.window, tuple(slot.monitor.rect)
        return
    legacy = getattr(board, "_legacy", None)
    if legacy is None:
        return
    width = int(getattr(app, "sw", 0) or 0)
    height = int(getattr(app, "sh", 0) or 0)
    yield legacy[0], (0, 0, width, height)


def _scale(app) -> None:
    if not ui_should_scale(set_dpi_aware()):
        return
    dpi = _window_dpi(app.root)
    if dpi is None or dpi == getattr(app, "_ui_dpi", None):
        return
    try:
        app.root.tk.call("tk", "scaling", tk_scaling(dpi))
        _reapply_fonts(app.root)
    except Exception:
        return
    app._ui_dpi = dpi
    for av in _bodies(app):
        av._draw_sig = None
        for ink in (getattr(av, "_inks", None) or {}).values():
            ink["sig"] = None


def _window_dpi(widget) -> int | None:
    if widget is None:
        return None
    return read_window_dpi(top_hwnd(widget))


def _reapply_fonts(widget) -> None:
    """Named Dungeon fonts, then every widget font, so Tk rebuilds point sizes."""
    try:
        import text_fonts as fonts

        fonts.reapply(widget)
    except Exception:
        pass
    _walk_fonts(widget)


def _walk_fonts(widget) -> None:
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        try:
            face = child.cget("font")
        except Exception:
            face = ""
        if face:
            try:
                child.configure(font=face)
            except Exception:
                pass
        _walk_fonts(child)


def _bodies(app) -> list:
    found = list(getattr(app, "avatars", {}).values())
    for subs in getattr(app, "sub_avatars", {}).values():
        found.extend(subs)
    found.extend(getattr(app, "_lingering_subs", []) or [])
    found.extend(getattr(app, "_dying_subs", []) or [])
    return found
