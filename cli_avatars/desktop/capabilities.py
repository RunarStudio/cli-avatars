"""Optional desktop libraries, and the one DPI call.

Imported before tkinter. ``set_dpi_aware()`` runs here, at import, before
any ``tk.Tk()``. ``HAS_PIL`` follows Pillow's ``Image`` module. ``ImageTk``
stays out of this package so the layer check still holds; the overlay
imports it when ``HAS_PIL`` is true.
"""

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
# edges only. DPI awareness must be set before tk.Tk() is created.
try:
    import win32 as w32
    HAS_W32 = True
    print(f"[INFO] DPI mode: {w32.set_dpi_aware()}")
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
