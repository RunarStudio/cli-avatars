"""
win32.py: thin ctypes layer over the Windows window manager.

No extra dependencies. See WINDOW-PERCHES-PLAN.md.

    set_dpi_aware()          call once, before tk.Tk()
    list_windows(skip)       visible windows, topmost first, real frame (no shadow)
    own_hwnds(*widgets)      top-level hwnds of our own tk windows, to skip

Smoke test: `python win32.py` prints a table of the real windows,
their perches, and how long one scan takes.
"""

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

if sys.platform != "win32":
    raise ImportError("win32.py only runs on Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

HWND = wintypes.HWND

# ── constants ────────────────────────────────────────────────────
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
SM_CXSCREEN, SM_CYSCREEN = 0, 1
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)

# ── signatures (64-bit safe) ─────────────────────────────────────
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
for _fn in ("IsWindowVisible", "IsIconic", "IsZoomed"):
    getattr(user32, _fn).argtypes = [HWND]
    getattr(user32, _fn).restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetAncestor.argtypes = [HWND, wintypes.UINT]
user32.GetAncestor.restype = HWND
user32.MonitorFromWindow.argtypes = [HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
dwmapi.DwmGetWindowAttribute.argtypes = [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long   # HRESULT


@dataclass(frozen=True)
class Win:
    hwnd: int
    title: str
    cls: str
    rect: tuple[int, int, int, int]   # left, top, right, bottom: visible frame, no shadow
    maximized: bool                   # IsZoomed, or covers its whole monitor (F11 / fullscreen)
    z: int                            # 0 = topmost


# ── DPI ──────────────────────────────────────────────────────────
def set_dpi_aware() -> str:
    """Make this process per-monitor DPI aware. Call before tk.Tk(). Returns the mode set."""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return "per-monitor-v2"
    except AttributeError:
        pass
    try:
        if ctypes.WinDLL("shcore").SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            return "system"
    except AttributeError:
        pass
    return "none"


def screen_rect() -> tuple[int, int, int, int]:
    """Primary screen rect, in the process's current DPI mode."""
    return (0, 0, user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN))


# ── small helpers ────────────────────────────────────────────────
def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _cloaked(hwnd) -> bool:
    val = wintypes.DWORD(0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    return hr == 0 and val.value != 0


def frame_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Visible frame without the invisible resize border / shadow. Falls back to GetWindowRect."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return (r.left, r.top, r.right, r.bottom)
    return window_rect(hwnd)


def window_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Raw GetWindowRect (includes the shadow border). Used for comparison and fallback."""
    r = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left, r.top, r.right, r.bottom)
    return None


def _monitor_rect(hwnd) -> tuple[int, int, int, int] | None:
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        m = mi.rcMonitor
        return (m.left, m.top, m.right, m.bottom)
    return None


# ── public API ───────────────────────────────────────────────────
def own_hwnds(*widgets) -> set[int]:
    """Top-level hwnds of our own tk windows (overlay, HUD, config), to skip."""
    out = set()
    for w in widgets:
        try:
            root = user32.GetAncestor(w.winfo_id(), GA_ROOT)
            if root:
                out.add(int(root))
        except Exception:
            pass
    return out


def _pid(hwnd) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def list_windows(skip: set[int] | frozenset = frozenset(), min_size: int = 80,
                 skip_own_process: bool = True) -> list[Win]:
    """Visible top-level windows, topmost first. Cheapest checks first.

    skip_own_process drops every window of this Python process (overlay, HUD,
    config, skins), so the full-screen overlay never hides the windows below it.
    """
    me = os.getpid()
    hwnds: list[int] = []

    @WNDENUMPROC
    def _cb(hwnd, _lp):
        hwnds.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)          # z-order, top to bottom

    wins: list[Win] = []
    for hwnd in hwnds:
        if not user32.IsWindowVisible(hwnd):
            continue
        if user32.IsIconic(hwnd):        # minimized: fast exit, no DWM call
            continue
        if hwnd in skip:
            continue
        if skip_own_process and _pid(hwnd) == me:
            continue
        title = _title(hwnd)
        if not title.strip():
            continue
        if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            continue
        cls = _class(hwnd)
        if cls in SKIP_CLASSES:
            continue
        if _cloaked(hwnd):               # other virtual desktop, suspended UWP
            continue
        rect = frame_rect(hwnd)
        if rect is None:
            continue
        l, t, r, b = rect
        if r - l < min_size or b - t < min_size:
            continue
        maximized = bool(user32.IsZoomed(hwnd)) or rect == _monitor_rect(hwnd)
        wins.append(Win(int(hwnd), title, cls, rect, maximized, len(wins)))
    return wins


# ── smoke test ───────────────────────────────────────────────────
def _smoke() -> None:
    import time
    from perchas import build_perches

    mode = set_dpi_aware()
    screen = screen_rect()
    wins = list_windows()

    print(f"DPI mode: {mode}   screen: {screen}   windows: {len(wins)}\n")
    print(f"{'z':>2}  {'max':3}  {'frame (DWM)':<26} {'shadow l/t/r/b':<16} title")
    for w in wins:
        raw = window_rect(w.hwnd) or w.rect
        sh = (w.rect[0] - raw[0], w.rect[1] - raw[1], raw[2] - w.rect[2], raw[3] - w.rect[3])
        print(f"{w.z:>2}  {'yes' if w.maximized else '':3}  {str(w.rect):<26} "
              f"{'/'.join(map(str, sh)):<16} {w.title[:50]}")

    perches = build_perches(wins, screen)
    titles = {w.hwnd: w.title for w in wins}
    print(f"\nPerches: {len(perches)}")
    for p in perches:
        print(f"  y={p.y:<5} x {p.x1}–{p.x2} ({p.length} px)  {titles[p.hwnd][:50]}")

    n = 20
    t0 = time.perf_counter()
    for _ in range(n):
        build_perches(list_windows(), screen)
    ms = (time.perf_counter() - t0) * 1000 / n
    print(f"\nOne scan (list_windows + build_perches): {ms:.2f} ms average over {n}")


if __name__ == "__main__":
    _smoke()
