"""Click-through for empty overlay pixels. Win32 bits live here.

``WS_EX_TRANSPARENT`` is set when the cursor is on the colour-key, and
cleared when it is on an avatar, bubble, or portal. Other overlays stay
click-through. The decision is pure. The style write is Windows-only.
"""

from __future__ import annotations

import sys

WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
_GWL_EXSTYLE = -20


def exstyle_for(style: int, pass_through: bool) -> int:
    """Layered always. Transparent only when the pixel should ignore the mouse."""
    bits = int(style) | WS_EX_LAYERED
    if pass_through:
        return bits | WS_EX_TRANSPARENT
    return bits & ~WS_EX_TRANSPARENT


def passes_through(x: float, y: float, boxes) -> bool:
    """True when ``(x, y)`` misses every ``(left, top, width, height)`` box."""
    for box in boxes:
        left, top, width, height = box
        if left <= x <= left + width and top <= y <= top + height:
            return False
    return True


def overlay_pass_through(cursor, rect, boxes) -> bool:
    """This overlay ignores the mouse. A cursor on another monitor stays through."""
    if cursor is None:
        return True
    x, y = cursor
    left, top, right, bottom = rect
    if not (left <= x <= right and top <= y <= bottom):
        return True
    return passes_through(x, y, boxes)


def has_transparent(style: int) -> bool:
    return bool(int(style) & WS_EX_TRANSPARENT)


def read_exstyle(hwnd: int) -> int | None:
    """Current extended style, or None off Windows."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes

        user = ctypes.WinDLL("user32", use_last_error=True)
        getter = getattr(user, "GetWindowLongPtrW", None) or user.GetWindowLongW
        getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
        getter.restype = ctypes.c_ssize_t
        return int(getter(int(hwnd), _GWL_EXSTYLE))
    except (OSError, AttributeError, ValueError, TypeError):
        return None


def apply_exstyle(hwnd: int, style: int) -> bool:
    """Write an extended style. False off Windows or when the hwnd is missing."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user = ctypes.WinDLL("user32", use_last_error=True)
        setter = getattr(user, "SetWindowLongPtrW", None) or user.SetWindowLongW
        setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        setter.restype = ctypes.c_ssize_t
        setter(int(hwnd), _GWL_EXSTYLE, int(style))
        return True
    except (OSError, AttributeError, ValueError, TypeError):
        return False


def set_pass_through(hwnd: int, pass_through: bool) -> bool:
    """Toggle ``WS_EX_TRANSPARENT`` and keep the rest of the style, including layered."""
    current = read_exstyle(hwnd)
    if current is None:
        return False
    return apply_exstyle(hwnd, exstyle_for(current, pass_through))


def cursor_point() -> tuple[int, int] | None:
    """Virtual cursor, or None off Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class _Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user = ctypes.WinDLL("user32", use_last_error=True)
        point = _Point()
        user.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
        user.GetCursorPos.restype = ctypes.c_int
        if not user.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)
    except (OSError, AttributeError, ValueError, TypeError):
        return None


def top_hwnd(widget) -> int:
    """Root hwnd for a Tk widget. 0 off Windows."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes

        hwnd = int(widget.winfo_id())
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user.GetAncestor.restype = ctypes.c_void_p
        root = user.GetAncestor(hwnd, 2)
        return int(root or hwnd)
    except (OSError, AttributeError, ValueError, TypeError):
        return 0


def format_style(style: int) -> str:
    """Bits a Windows check can read without moving the mouse."""
    bits = int(style)
    flags = []
    if bits & WS_EX_TRANSPARENT:
        flags.append("TRANSPARENT")
    if bits & WS_EX_LAYERED:
        flags.append("LAYERED")
    if bits & 0x00000080:
        flags.append("TOOLWINDOW")
    names = ",".join(flags) if flags else "none"
    return f"exstyle=0x{bits:08X} {names}"


def describe_running() -> str:
    """Styles of overlay windows that are already open. Does not move the cursor."""
    if sys.platform != "win32":
        return "click-through: skipped"
    titles = _overlay_titles()
    if not titles:
        return "click-through: no overlay window"
    lines = []
    for hwnd, title in titles:
        style = read_exstyle(hwnd)
        if style is None:
            lines.append(f"{title} exstyle=unreadable")
        else:
            lines.append(f"{title} {format_style(style)}")
    return "\n".join(lines)


def _overlay_titles() -> list[tuple[int, str]]:
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _visit(hwnd, _lparam):
        length = user.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title.startswith("CLI Avatars overlay"):
            found.append((int(hwnd), title))
        return True

    user.EnumWindows.argtypes = [type(_visit), wintypes.LPARAM]
    user.EnumWindows.restype = ctypes.c_bool
    user.EnumWindows(_visit, 0)
    return found


if __name__ == "__main__":
    print(describe_running())
