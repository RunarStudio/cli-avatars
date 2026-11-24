"""Child process for ``test_close_choice``: the close picker and tray off a real Tk root. Exit 77 without a display.

    python tests/_close_probe.py <repo root>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import json
import sys
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import close_choice  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.hud_window import _show_hud_win  # noqa: E402
from webui import server  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


class FakeTray:
    def __init__(self, visible=True):
        self.visible = visible
        self.notes = []

    def notify(self, message, title=None):
        self.notes.append(message)


def pump(times: int = 5) -> None:
    for _ in range(times):
        root.update()


def close_x() -> None:
    root.tk.call(root.protocol("WM_DELETE_WINDOW"))
    pump()


def key(widget, name: str) -> None:
    widget.focus_force()
    pump()
    widget.event_generate(f"<KeyPress-{name}>")
    pump()


def serves(httpd) -> bool:
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    try:
        urllib.request.urlopen(url, timeout=3).close()
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


def toplevels() -> list:
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


data = Path(tempfile.mkdtemp())
quits: list = []
app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=lambda: quits.append("quit"), _toggle_rooms=noop,
    _toggle_chat=noop, _create_hud_win=noop, _rooms_shown=True, _chat_shown=False,
    _config_path=data / "config.json", _tray=FakeTray(),
    _phone_server=server.start(data, "127.0.0.1", 0)[0],
)
app._show_hud_win = lambda: _show_hud_win(app)
app.dungeon = DungeonWindow(app)
app.dungeon.build(offscreen=True)
root.geometry("800x520+40+30")
root.deiconify()
pump()
before = toplevels()

close_x()
panel = close_choice.picker(app)
check("close asks", panel is not None and quits == [] and root.state() == "normal")
check("picker in window", panel.winfo_toplevel() is root and toplevels() == before)

key(panel, "Escape")
check("esc cancels", close_choice.picker(app) is None and quits == [] and root.state() == "normal")

close_x()
close_choice.picker(app).choose("quit")
pump()
check("close quits", quits == ["quit"] and close_choice.picker(app) is None)
quits.clear()

rect = root.geometry()
close_x()
key(close_choice.picker(app), "Return")
check("enter minimizes", root.state() == "withdrawn" and quits == [], root.state())
ticks: list = []
root.after(20, lambda: ticks.append(1))
for _ in range(40):
    root.update()
    root.after(5)
check("loop runs hidden", ticks == [1] and serves(app._phone_server))
check("notice once", len(app._tray.notes) == 1, str(app._tray.notes))

app._show_hud_win()
pump()
check("show restores", root.state() == "normal" and root.geometry() == rect, root.geometry() + " " + rect)

close_x()
picked = close_choice.picker(app)
picked.remember.set(True)
picked.choose("minimize")
pump()
saved = json.loads(app._config_path.read_text(encoding="utf-8"))
app._show_hud_win()
pump()
close_x()
check("remember minimize", saved["desktop"]["on_close"] == "minimize" and close_choice.picker(app) is None
      and root.state() == "withdrawn" and len(app._tray.notes) == 1, str(saved))
app._show_hud_win()
pump()

host = tk.Frame(root)
var = close_choice.mount_setting(app, host)
check("settings row", var.get() == close_choice.LABELS["minimize"], var.get())
var.set(close_choice.LABELS["quit"])
pump()
close_x()
check("remember quit", quits == ["quit"] and close_choice.picker(app) is None)
quits.clear()
var.set(close_choice.LABELS["ask"])
pump()
host.destroy()

app._tray = None
iconified: list = []
real_iconify = root.iconify
root.iconify = lambda: iconified.append(1)  # Xvfb has no window manager to honour a real iconify.
close_x()
close_choice.picker(app).choose("minimize")
pump()
check("no tray iconifies", iconified == [1] and root.state() != "withdrawn", root.state())
root.iconify = real_iconify

items_seen: list = []
fake = types.ModuleType("pystray")


class MenuItem:
    def __init__(self, text, action, default=False, enabled=None, checked=None):
        self.text, self.action, self.default = text, action, default


class Menu:
    SEPARATOR = MenuItem("-", None)

    def __init__(self, *items):
        self.items = items
        items_seen.extend(items)


class Icon(FakeTray):
    def __init__(self, name, image, title, menu, on_activate=None):
        super().__init__(visible=False)
        self.menu, self.on_activate = menu, on_activate

    def run(self):
        self.visible = True

    def stop(self):
        self.visible = False


fake.MenuItem, fake.Menu, fake.Icon = MenuItem, Menu, Icon
sys.modules["pystray"] = fake
from cli_avatars.desktop.tray import setup_tray  # noqa: E402

app._door_label = "Door: open"
app._toggle_door = app._call_home = app._update_app = noop
app._update_block = ""
setup_tray(app)
pump()
labels = [item.text for item in items_seen]
first = items_seen[0]
check("tray menu", first.text == "Show Dungeon" and first.default and "Quit" in labels
      and "Call home" in labels, str(labels))

close_x()
close_choice.picker(app).choose("minimize")
pump()
hidden = root.state()
first.action(app._tray, first)
pump()
check("tray show", hidden == "withdrawn" and root.state() == "normal", hidden + " " + root.state())
quit_item = next(item for item in items_seen if item.text == "Quit")
quit_item.action(app._tray, quit_item)
pump()
check("tray quit", quits == ["quit"])
server.stop(app._phone_server)
root.destroy()
