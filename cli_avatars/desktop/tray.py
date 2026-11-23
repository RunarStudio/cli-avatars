"""System-tray icon. Menu callbacks are injected via the app.

Each callback is scheduled with ``root.after(0, ...)`` so pystray's thread
never touches Tk widgets directly.
"""

import threading

from bundle_paths import asset_path

from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.paths import images_dir

if HAS_PIL:
    try:
        from PIL import Image
    except ImportError:
        HAS_PIL = False


def _setup_tray(self):
    if not HAS_PIL:
        return
    try:
        import pystray
        caine_path = asset_path("Caine_Icon.png")
        if not caine_path.exists():
            caine_path = images_dir() / "Caine_Icon.png"
        if caine_path.exists():
            icon_img = Image.open(str(caine_path)).convert("RGBA").resize((32, 32), Image.NEAREST)
        else:
            icon_img = Image.new("RGBA", (32, 32), (68, 136, 255, 255))
        menu = pystray.Menu(
            pystray.MenuItem("Skins",       lambda icon, item: self.root.after(0, self._open_skin_picker)),
            pystray.MenuItem("Config",      lambda icon, item: self.root.after(0, self._open_config_screen)),
            pystray.MenuItem("Show Status", lambda icon, item: self.root.after(0, self._show_hud_win)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Close",       lambda icon, item: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon(
            "AI Overlay", icon_img, "AI Overlay", menu,
            on_activate=lambda icon: self.root.after(0, self._bring_all_to_front),
        )
        threading.Thread(target=self._tray.run, daemon=True).start()
    except Exception as e:
        print(f"[overlay] tray icon failed: {e}")
        self._tray = None


def setup_tray(app):
    return _setup_tray(app)
