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
            pystray.MenuItem("Show Dungeon", lambda icon, item: self.root.after(0, self._show_hud_win)),
            pystray.MenuItem(self._door_label, lambda icon, item: self.root.after(0, self._toggle_door)),
            pystray.MenuItem("Call home", lambda icon, item: self.root.after(0, self._call_home)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",         lambda icon, item: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon(
            "Dungeon", icon_img, "Dungeon", menu,
            on_activate=lambda icon: self.root.after(0, self._show_hud_win),
        )
        threading.Thread(target=self._tray.run, daemon=True).start()
    except Exception as e:
        print(f"[overlay] tray icon failed: {e}")
        self._tray = None


def setup_tray(app: object) -> None:
    return _setup_tray(app)
