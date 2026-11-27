"""Child process for ``test_friday_chart``: on a Friday the Backlog boss burn-down parchment lies on the Dungeon
floor; a floor click under it still walks the keeper, and its scroll button still hides it. Made-up data; exit 77
without a display.

    python tests/_friday_chart_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import boss_view, cues, dungeon_nav, inside_roster, you_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from routing import PointerGesture  # noqa: E402

DATA = Path(sys.argv[2])


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


cues.play = lambda _app, _name: None
(DATA / "config.json").write_text('{"park": {"enabled": false}, "idle_props": {"enabled": false}}', encoding="utf-8")
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
model.open(sr.MAIN, "claude", "moon-forge")
model.open(sr.SIMPLE, "claude", "glass-orchard")
day = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
clock = [(day + timedelta(days=(4 - day.weekday()) % 7)).timestamp()]
canvas = tk.Canvas(root, width=1200, height=760, highlightthickness=0, bd=0)
canvas.pack()
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(clock[0]))
dungeon = SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _schedule_save=lambda: None)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={}, _chat_directory=lambda: DATA, scanner=SimpleNamespace(get_agents=lambda: {}),
    dungeon=dungeon, _session_rooms=model, _gesture=PointerGesture(), _nav=None, _grabbed=None,
    _open_chat_for_avatar=lambda av: None)
dungeon.app = app
book = PlaceBook(app, path=None)
app.places = book
hall = inside_roster.hall(book)
hall._talk = lambda: []
root.update()
dungeon_nav.attach(dungeon)
canvas._rooms_painter.paint(canvas)


def tick(seconds: float, step: float = 0.05) -> None:
    for _ in range(max(1, round(seconds / step))):
        clock[0] += step
        book._now = clock[0]
        book.draw_inside()


tick(0.5)
boss = boss_view.view_for(book)
check("friday shows the chart", time.localtime(clock[0]).tm_wday == 4 and "chart" in boss._items, boss._items)
# pan the Apothecary to the left edge: the pit leaves the view and the chart pins there, over the room
painter, plan = canvas._rooms_painter, hall.plan()
x, y = painter.to_canvas(*plan.floor("Apothecary").centre())
canvas._camera.move(round(120 - x), round(300 - y))
painter.paint(canvas)
tick(0.2)
x0, y0, x1, y1 = canvas.bbox(boss._items["chart"])
under = []
for y in range(y0 + 6, y1 - 6, 6):
    for x in range(x0 + 6, x1 - 6, 6):
        tile = painter.to_tile(x, y)
        room = plan.room_at(*tile) if tile is not None else None
        floor = plan.floor(room or "")
        if room and floor is not None and not floor.corridor and floor.holds(*tile):
            under.append((x, y, room))
check("the chart lies on a room's floor", bool(under), (x0, y0, x1, y1))
x, y, room = under[len(under) // 2]
pointer = InputController(app)
press = SimpleNamespace(x=x, y=y, x_root=x, y_root=y)
pointer.on_scene_press(press)
pointer.on_scene_release(press)
check("a floor click under the chart walks", USER_ID in hall._trips, f"{room} at {(x, y)}")
tick(12.0)
check("the keeper arrives under the chart", plan.room_at(*hall._feet[USER_ID]) == room, hall._feet[USER_ID])
check("the chart stays up", "chart" in boss._items)
bx0, by0, bx1, by1 = canvas.bbox(boss._items["btn"])
check("its scroll button keeps its click", you_view._clickable(canvas, (bx0 + bx1) / 2, (by0 + by1) / 2))
boss._click("chart")
tick(0.2)
check("the scroll button hides it", "chart" not in boss._items)
root.destroy()
print("done")
