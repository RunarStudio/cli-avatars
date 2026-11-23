"""Win32 window chrome. Other platforms no-op.

Dark title bars and un-owning an overlay live here so app code does not
touch ``windll``. A failure leaves the stock frame and the stock owner.
"""

from __future__ import annotations

import sys

# Distinct from the framed Dungeon so the two top-level windows do not share a title.
OVERLAY_TITLE = "CLI Avatars overlay"
# GWL_EXSTYLE / WS_EX_TOOLWINDOW. Keeps the borderless overlay out of Alt-Tab and the taskbar.
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080


def overlay_title(index: int) -> str:
    """Title for one overlay. ``index`` is that monitor's place in the layout."""
    return f"{OVERLAY_TITLE} {int(index)}"


def use_dark_titlebar(widget) -> None:
    """Ask DWM for an immersive dark title bar. Ignored off Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = _top_hwnd(widget)
        if not hwnd:
            return
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        set_attr = dwm.DwmSetWindowAttribute
        set_attr.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        set_attr.restype = ctypes.c_long
        value = ctypes.c_int(1)
        # 20 is DWMWA_USE_IMMERSIVE_DARK_MODE. 19 is the same flag on older builds.
        for attr in (20, 19):
            if set_attr(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                return
    except (OSError, AttributeError, ValueError, TypeError):
        return


def mark_toolwindow(widget) -> None:
    """Set ``WS_EX_TOOLWINDOW`` on the top-level overlay. Ignored off Windows.

    The bit is applied to the root hwnd. Tk's overrideredirect window otherwise
    keeps a taskbar and Alt-Tab entry when it has a title.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = _top_hwnd(widget)
        if not hwnd:
            return
        user = ctypes.WinDLL("user32", use_last_error=True)
        getter = getattr(user, "GetWindowLongPtrW", None) or user.GetWindowLongW
        setter = getattr(user, "SetWindowLongPtrW", None) or user.SetWindowLongW
        getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
        getter.restype = ctypes.c_ssize_t
        setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        setter.restype = ctypes.c_ssize_t
        current = getter(hwnd, _GWL_EXSTYLE)
        setter(hwnd, _GWL_EXSTYLE, int(current) | _WS_EX_TOOLWINDOW)
    except (OSError, AttributeError, ValueError, TypeError):
        return


def detach_overlay(widget) -> None:
    """Stop a topmost overlay from hiding when the Dungeon is minimized.

    Tk owns each ``Toplevel`` by the root. On Windows that owner relationship
    iconifies the overlay with the root. Clearing it keeps desktop avatars
    on screen. The overlay stays in this process.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winfo_id())
        user = ctypes.WinDLL("user32", use_last_error=True)
        # GWLP_HWNDPARENT. 32-bit Windows only has SetWindowLongW.
        setter = getattr(user, "SetWindowLongPtrW", None) or user.SetWindowLongW
        setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
        setter(hwnd, -8, 0)
    except (OSError, AttributeError, ValueError, TypeError):
        return


def _top_hwnd(widget) -> int:
    import ctypes

    hwnd = int(widget.winfo_id())
    root = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
    return int(root or hwnd)
