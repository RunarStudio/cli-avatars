"""Child process for ``test_door_bugs``: real ``main()`` quits by picker, by on_close=quit or by the tray. Exit 77 without a display.

    python tests/_quit_probe.py <repo root> <temp dir> <picker|setting|tray>

Fixtures only: a pystray stand-in, a stuck room run, no bot source, loopback port 0. Prints ``trigger <unix time>`` and
``ok <check>``; a failed check exits 1.
"""

import atexit
import json
import os
import socket
import sys
import threading
import time
import types
from pathlib import Path

repo, tmp, how = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, repo)
os.environ["CLI_AVATARS_DATA_DIR"] = str(tmp / "data")
os.environ["CLI_AVATARS_PORT"] = "0"
try:
    import tkinter as tk

    tk.Tk().destroy()
except Exception:
    raise SystemExit(77)


class MenuItem:
    def __init__(self, text, action, default=False, enabled=None, checked=None):
        self.text, self.action = text, action


class Menu:
    SEPARATOR = MenuItem("-", None)

    def __init__(self, *items):
        self.items = items


class Icon:
    """Like the win32 backend: ``run`` pumps until ``stop``."""

    def __init__(self, name, image, title, menu, on_activate=None):
        self.menu, self.visible, self.running = menu, False, False
        self._msg = threading.Event()

    def run(self):
        self.running = self.visible = True
        self._msg.wait()
        self.visible = False

    def stop(self):
        self.running = False
        self._msg.set()

    def notify(self, *_args, **_kwargs):
        return None


sys.modules["pystray"] = types.SimpleNamespace(MenuItem=MenuItem, Menu=Menu, Icon=Icon)


class NoBots:
    def __init__(self):
        raise RuntimeError("no bot source in a test")


import bots.service  # noqa: E402
import chat_window  # noqa: E402

bots.service.BotService = NoBots

import cli_avatars.app.shell as shell  # noqa: E402
from cli_avatars.app import close_choice  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from cli_avatars.world.scanner import SessionScanner  # noqa: E402

config = tmp / "config.json"
config.write_text(json.dumps({
    "dungeon": {"door": "open"},
    "desktop": {"bootcheck": False, "on_close": "ask" if how == "picker" else "quit"},
    "web": {"enabled": True, "bind": "127.0.0.1", "port": 0},
}))
shell.CONFIG_PATH = config
SessionScanner.loop = lambda self: None


class Stuck:
    """A room run whose child never lets go of its pipe."""

    stopped = False

    def stop(self):
        self.stopped = True

    def wait(self, timeout=None):
        time.sleep(timeout or 0)
        raise TimeoutError("room process is still running")


stuck = Stuck()
seen = {}


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}", flush=True)
        raise SystemExit(1)
    print(f"ok {name}", flush=True)


def trigger(app):
    seen["app"], seen["port"] = app, app._phone_server.server_address[1]
    cli_runner._RUNS[("fixture-room", "fixture")] = stuck
    chat_window._STOP_ON_EXIT.append(atexit.register(cli_runner.stop_all))
    real = app._quit

    def quit_and_look():
        real()
        seen["state"] = app.root.state()

    app._quit = quit_and_look
    print(f"trigger {time.time():.3f}", flush=True)
    if how == "tray":
        item = [i for i in app._tray.menu.items if i.text == "Quit"][0]
        threading.Thread(target=lambda: item.action(app._tray, item), daemon=True).start()
    elif how == "picker":
        close_choice.request_close(app)
        app.root.update()
        close_choice.picker(app).choose("quit")
    else:
        close_choice.request_close(app)


start = shell.OverlayApp.__init__


def init(self):
    start(self)
    self.root.after(2500, lambda: trigger(self))


shell.OverlayApp.__init__ = init
from cli_avatars.app.main import main  # noqa: E402

code = main([])
app = seen["app"]
check("main returned", code == 0, str(code))
check("window gone at once", seen.get("state") == "withdrawn", str(seen.get("state")))
check("tray stopped", not app._tray.running)
check("run stopped", stuck.stopped)
with socket.socket() as probe:
    probe.settimeout(0.5)
    check("phone server closed", probe.connect_ex(("127.0.0.1", seen["port"])) != 0)
live = [t.name for t in threading.enumerate() if t.is_alive() and not t.daemon and t is not threading.main_thread()]
check("no thread holds the exit", live == [], str(live))
