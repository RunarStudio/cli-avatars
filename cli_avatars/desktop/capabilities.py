"""Optional desktop libraries, and the one DPI call.

``desktop_escape_available`` is Windows only. Linux and macOS have no
colour-key overlay, so avatars stay in the Dungeon.

Imported before tkinter. ``set_dpi_aware()`` runs here, at import, before
any ``tk.Tk()``. ``HAS_PIL`` follows Pillow's ``Image`` module. ``ImageTk``
stays out of this package so the layer check still holds; the overlay
imports it when ``HAS_PIL`` is true.
"""

import os

from cli_avatars.desktop.dpi import set_dpi_aware


def desktop_escape_available() -> bool:
    """True when an overlay can leave the Dungeon. Windows only."""
    return os.name == "nt"

HAS_WINCTL = False
HAS_W32 = False
HAS_PIL = False
pwc = None
w32 = None

try:
    import pywinctl as pwc
    HAS_WINCTL = True
except ImportError:
    pwc = None
    print("[WARN] pywinctl not installed — window terrain disabled.")
    print("       Install: pip install pywinctl")

# Window perches (WINDOW-PERCHES-PLAN.md): real frames via DWM, visible top
# edges only. DPI awareness is set here, after pywinctl's import and before
# tk.Tk(). desktop.dpi is the helper the monitor list calls too.
_DPI_MODE = set_dpi_aware()

try:
    import win32 as w32
    HAS_W32 = True
    print(f"[INFO] DPI mode: {_DPI_MODE}")
except Exception as _w32_err:
    w32 = None
    HAS_W32 = False
    print(f"[WARN] win32 perches unavailable ({_w32_err}) — falling back to pywinctl.")

try:
    from PIL import Image as _Image  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow not installed — using fallback rectangles.")
    print("       Install: pip install pillow")
