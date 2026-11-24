"""Process DPI awareness. One helper for the overlay and the monitor list.

Call ``set_dpi_aware`` before the first ``tk.Tk()`` and before any monitor
query. The result is cached: Windows accepts the call only once, and a
second call would report ``none`` even though the process is already aware.

The ladder prefers per-monitor v2 (``SetProcessDpiAwarenessContext(-4)``),
then per-monitor (``SetProcessDpiAwareness(2)``), then system
(``SetProcessDPIAware``). The call shape matches the one the overlay already
used. A different spelling can make v2 succeed where this one falls through
to system, and Tk 8.6 then sizes the overlay in a different space from the
Win32 rects. Keeping this ladder keeps both in the mode the process actually
got (system, on a 125% display where v2 does not stick).
"""

import ctypes
import sys

_MODE: str | None = None


def reset_dpi_state() -> None:
    """Forget the cached mode. Tests use this; the app calls it never."""
    global _MODE
    _MODE = None


def read_window_dpi(hwnd: int) -> int | None:
    """``GetDpiForWindow`` for the Dungeon. None off Windows or when the hwnd is missing.

    The monitor signature does not change when a window is dragged between
    monitors, so the text scale follows this value.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        user.GetDpiForWindow.restype = ctypes.c_uint
        value = int(user.GetDpiForWindow(int(hwnd)))
    except (OSError, AttributeError, ValueError, TypeError):
        return None
    if value < 1:
        return None
    return value


def set_dpi_aware() -> str:
    """Set awareness once. Returns ``per-monitor-v2``, ``per-monitor``, ``system``, ``none``, or ``skipped``."""
    global _MODE
    if _MODE is not None:
        return _MODE
    if sys.platform != "win32":
        _MODE = "skipped"
        return _MODE
    _MODE = _apply()
    return _MODE


def _apply() -> str:
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_ctx = user32.SetProcessDpiAwarenessContext
        set_ctx.argtypes = [ctypes.c_void_p]
        set_ctx.restype = ctypes.c_int
        if set_ctx(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_aw = shcore.SetProcessDpiAwareness
        set_aw.argtypes = [ctypes.c_int]
        set_aw.restype = ctypes.c_long
        if set_aw(2) == 0:
            return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        aware = user32.SetProcessDPIAware
        aware.argtypes = []
        aware.restype = ctypes.c_int
        if aware():
            return "system"
    except (AttributeError, OSError):
        pass
    return "none"
