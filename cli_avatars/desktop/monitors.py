"""Windows monitor list, DPI, and the layout signature.

Pure records live here so Linux can import the module. Enumeration runs
only on Windows, and only when ``list_monitors`` is called. The geometry
(grounds, shared edges, step-up) is in ``cli_avatars.world.monitors``,
which this module does not import.

Smoke, from the repo root::

    python -m cli_avatars.desktop.monitors
    python -m cli_avatars.world.monitors --png layout.png

The first prints the live monitors and the signature. The second prints
grounds, ceilings and passable edges, and writes the debug PNG.
"""

import hashlib
import sys
from dataclasses import dataclass

# MONITORINFOEXW.szDevice is CCHDEVICENAME wide.
_DEVICE_CHARS = 32
_MONITORINFOF_PRIMARY = 1
_MDT_EFFECTIVE_DPI = 0
_DEFAULT_DPI = 96


@dataclass(frozen=True)
class Monitor:
    """One display. ``id`` is a short hash of the device name, not the name.

    ``rect`` and ``work`` are ``(left, top, right, bottom)`` in virtual px.
    The same fields exist on ``cli_avatars.world.monitors.Monitor``. This
    module cannot import that one: desktop code does not import world.
    """

    id: str
    rect: tuple[int, int, int, int]
    work: tuple[int, int, int, int]
    dpi: int
    primary: bool


def monitor_id(device_name: str) -> str:
    """First 8 hex characters of SHA-1 over the UTF-8 device name."""
    text = device_name.encode("utf-8")
    return hashlib.sha1(text).hexdigest()[:8]


def monitor_signature(monitors) -> str:
    """First 12 hex characters of SHA-1 over the sorted monitor rows.

    Each row is ``left,top,right,bottom,dpi,primary`` with primary as ``1``
    or ``0``. Rows are sorted by those integers and joined with ``;``.
    Device names and monitor ids are not part of the hash.
    """
    rows = []
    for monitor in monitors:
        left, top, right, bottom = (int(v) for v in monitor.rect)
        primary = 1 if monitor.primary else 0
        rows.append((left, top, right, bottom, int(monitor.dpi), primary))
    rows.sort()
    payload = ";".join(f"{left},{top},{right},{bottom},{dpi},{flag}" for left, top, right, bottom, dpi, flag in rows)
    return hashlib.sha1(payload.encode("ascii")).hexdigest()[:12]


def _fit_work(rect: tuple[int, int, int, int], work: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Work area clipped inside ``rect``. A degenerate work area becomes ``rect``."""
    left, top, right, bottom = rect
    wl, wt, wr, wb = work
    if wr <= wl or wb <= wt:
        return rect
    wl, wr = max(wl, left), min(wr, right)
    wt, wb = max(wt, top), min(wb, bottom)
    if wr <= wl or wb <= wt:
        return rect
    return (wl, wt, wr, wb)


def _as_rect(values) -> tuple[int, int, int, int]:
    left, top, right, bottom = (int(v) for v in values)
    return (left, top, right, bottom)


def monitors_from_raw(rows) -> list[Monitor]:
    """Build monitors from ``(device_name, rect, work, dpi, primary)`` rows.

    The device name is hashed into ``id`` and dropped. A repeated name gets
    a ``-2``, ``-3``, … suffix so ids stay unique. Dpi below 1 becomes 96.
    Primary monitors come first, then left-to-right.
    """
    built: list[Monitor] = []
    seen: dict[str, int] = {}
    for device, rect_raw, work_raw, dpi_raw, primary in rows:
        rect = _as_rect(rect_raw)
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        name = str(device or "").replace("\x00", "").strip()
        if not name:
            name = "rect:" + ",".join(str(v) for v in rect)
        base = monitor_id(name)
        seen[base] = seen.get(base, 0) + 1
        ident = base if seen[base] == 1 else f"{base}-{seen[base]}"
        dpi = int(dpi_raw)
        if dpi < 1:
            dpi = _DEFAULT_DPI
        built.append(Monitor(
            id=ident,
            rect=rect,
            work=_fit_work(rect, _as_rect(work_raw)),
            dpi=dpi,
            primary=bool(primary),
        ))
    built.sort(key=lambda m: (0 if m.primary else 1, m.rect[0], m.rect[1], m.rect[2], m.rect[3], m.id))
    return built


def list_monitors() -> list[Monitor]:
    """Live monitors. An empty list on Linux, or when enumeration fails."""
    if sys.platform != "win32":
        return []
    try:
        return _enum_win32()
    except (OSError, AttributeError, ValueError):
        return []


def _enum_win32() -> list[Monitor]:
    """``EnumDisplayMonitors`` + ``GetMonitorInfoW`` + effective DPI.

    Prototypes are separate function pointers so this does not replace
    argtypes that ``win32.py`` already set on the shared user32 handle.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hmonitor = getattr(wintypes, "HMONITOR", ctypes.c_void_p)
    hdc = getattr(wintypes, "HDC", ctypes.c_void_p)
    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, hmonitor, hdc, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )
    enum_monitors = ctypes.WINFUNCTYPE(
        wintypes.BOOL, hdc, ctypes.c_void_p, enum_proc, wintypes.LPARAM,
    )(("EnumDisplayMonitors", user32))
    get_info = ctypes.WINFUNCTYPE(
        wintypes.BOOL, hmonitor, ctypes.c_void_p,
    )(("GetMonitorInfoW", user32))

    class _MonitorInfoExW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", ctypes.c_wchar * _DEVICE_CHARS),
        ]

    handles: list[int] = []

    @enum_proc
    def _collect(handle, _hdc, _rect, _data):
        # Copy the address now. The callback argument must not be kept as a
        # live pointer: the next call can reuse that slot.
        if handle:
            handles.append(int(handle))
        return True

    if not enum_monitors(None, None, _collect, 0):
        if not handles:
            raise OSError(ctypes.get_last_error(), "EnumDisplayMonitors failed")

    dpi_for = _dpi_getter()
    rows = []
    for handle in handles:
        info = _MonitorInfoExW()
        info.cbSize = ctypes.sizeof(_MonitorInfoExW)
        if not get_info(handle, ctypes.byref(info)):
            continue
        rect = _box(info.rcMonitor)
        work = _box(info.rcWork)
        rows.append((
            info.szDevice,
            rect,
            work,
            dpi_for(handle),
            bool(info.dwFlags & _MONITORINFOF_PRIMARY),
        ))
    return monitors_from_raw(rows)


def _box(rect) -> tuple[int, int, int, int]:
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def _dpi_getter():
    """``GetDpiForMonitor(MDT_EFFECTIVE_DPI)``, or 96 when shcore is missing."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return lambda _handle: _DEFAULT_DPI
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        hmonitor = getattr(wintypes, "HMONITOR", ctypes.c_void_p)
        getter = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            hmonitor,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        )(("GetDpiForMonitor", shcore))
    except (OSError, AttributeError):
        return lambda _handle: _DEFAULT_DPI

    def _read(handle) -> int:
        dpi_x = wintypes.UINT(0)
        dpi_y = wintypes.UINT(0)
        hr = getter(handle, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        if hr != 0 or dpi_x.value < 1:
            return _DEFAULT_DPI
        return int(dpi_x.value)

    return _read


def format_monitors(monitors) -> str:
    """Text table for the smoke command. No device names."""
    lines = [
        f"monitors: {len(monitors)}",
        f"signature: {monitor_signature(monitors)}",
    ]
    if not monitors:
        if sys.platform != "win32":
            lines.append("Windows EnumDisplayMonitors is not available on this machine.")
        else:
            lines.append("No monitors returned.")
        return "\n".join(lines)
    for monitor in monitors:
        flag = "yes" if monitor.primary else "no"
        lines.append(
            f"{monitor.id}  primary={flag}  dpi={monitor.dpi}  "
            f"rect={monitor.rect}  work={monitor.work}"
        )
    lines.append("grounds and edges: python -m cli_avatars.world.monitors --png layout.png")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the live monitor list. ``argv`` is ignored; there are no flags."""
    del argv
    print(format_monitors(list_monitors()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
