"""Child process for ``test_dungeon_layout``: the Dungeon window narrowed and widened, splitters dragged.

    python tests/_dungeon_layout_probe.py <repo root> <temp dir>

Prints ``ok <check>`` per check; any failed check exits 1. Exit 77 when Tk has no display.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import dungeon_sash, session_rooms  # noqa: E402
from cli_avatars.app.dungeon_geom import SCENE_MIN  # noqa: E402
from cli_avatars.app.dungeon_rooms import fit_scale  # noqa: E402
from cli_avatars.app.dungeon_store import load_store  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402

DATA = Path(sys.argv[2])
host = OverlayApp.__new__(OverlayApp)
host.root = root
host.config = {"sound": {"cues": False}}
host._config_path = DATA / "config.json"
for key, value in dict(_rooms_shown=True, _chat_shown=False, _rooms_btn=None, _chat_btn=None, _rooms_sig=None,
                       _rooms_thumbs={}, _rooms_warns={}, _bot_photos=[], _bot_vars=[], _topics_stamp=None,
                       sub_avatars={}, desktop_escape=False).items():
    setattr(host, key, value)
host.scanner = SimpleNamespace(get_agents=lambda: {}, bubbles=BubbleBoard(), _events=SimpleNamespace(data_dir=DATA))
host._session_rooms = session_rooms.SessionRooms(None)
host._session_rooms.open("simple", "claude", "harbor-map")
view = host.dungeon = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def size(w: int, h: int) -> None:
    root.geometry(f"{w}x{h}+20000+20000")
    for _ in range(4):
        root.update()


def widths() -> tuple:
    return view._left.winfo_width(), view._right.winfo_width(), view._mid.winfo_width()


def body_right() -> int:
    body = view._mid.master
    return body.winfo_rootx() + body.winfo_width()


size(1400, 800)
left, right, mid = widths()
check("wide window keeps the chosen widths", (left, right) == (280, 360), widths())

size(760, 560)
left, right, mid = widths()
check("narrow window shrinks the docks, map keeps room", mid >= SCENE_MIN and left < 280 and right < 360, widths())
painter = view.scene._rooms_painter
box = (view.scene.winfo_width(), view.scene.winfo_height())
check("map refits to the narrow pane",
      painter._scale == fit_scale(painter.base().size, box) and painter._center == (box[0] // 2, box[1] // 2),
      (painter._scale, painter._center, box))

size(1400, 800)
check("wide again restores the chosen widths", widths()[:2] == (280, 360), widths())

view.drag_dock(view._right, SimpleNamespace(x_root=body_right() - 480, y_root=0, x=0, y=0), 200, 720)
size(1400, 800)
check("right splitter drag widens the chat", view._right.winfo_width() == 480, widths())

view.drag_dock(view._right, SimpleNamespace(x_root=body_right() - 20, y_root=0, x=0, y=0), 200, 720)
size(1400, 800)
check("collapsed column keeps a thin edge",
      not view._right_open and not view._right.winfo_ismapped() and view._sash_r.winfo_ismapped()
      and view._mid.winfo_width() > 1400 - 280 - 40, (view._right_open, widths()))

bound = bool(view._sash_r.bind("<Double-Button-1>"))
dungeon_sash.reset(view, "right")
size(1400, 800)
check("double-click resets the default width",
      bound and view._right_open and view._right.winfo_width() == 360, widths())

view._offscreen, view._placed, view._signature = False, True, "abcdef012345"
view.drag_dock(view._left, SimpleNamespace(x_root=view._mid.master.winfo_rootx() + 330, y_root=0, x=0, y=0), 160, 640)
size(1400, 800)
view.save_now()
stored = load_store(view._path()).layouts["abcdef012345"]
view._left.configure(width=200)
view._apply_saved_docks(stored, 1400)
size(1400, 800)
check("widths survive a restart", (view._left.winfo_width(), view._right.winfo_width()) == (330, 360), widths())
root.destroy()
