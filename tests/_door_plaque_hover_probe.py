"""Child process for ``test_door_plaque``: the pointer rests on a plaque's edge, next to its tip. Exit 77 without Tk.

    python tests/_door_plaque_hover_probe.py <repo root> <data dir>

Prints ``ok <check>``; a failed check, or a show/leave loop, exits 1.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import cues, door_plaque, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.app.throttle import StoreThrottle  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from topics import set_topic  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


data = Path(sys.argv[2])
clock = [1_795_000_000.0]
played = []
cues._player = lambda name, app: played.append(name)
model = sr.SessionRooms(data / "ui" / "session_rooms.json")
model.open(sr.MAIN, "claude", "moon-forge")
model.open(sr.SIMPLE, "claude", "glass-orchard")
for topic in ("moon-forge", "glass-orchard"):
    set_topic(data, topic, title=topic, project="lantern", status="open")
agents = {"a1b2c3d4": AgentInfo("a1b2c3d4", "Quill", status="busy", source="claude", project="moon-forge",
                                subagents=2, last_seen=clock[0]),
          "e5f6a7b8": AgentInfo("e5f6a7b8", "Owl", status="idle", source="claude", project="glass-orchard",
                                last_seen=clock[0])}
root.geometry("900x700+0+0")
canvas = tk.Canvas(root, width=900, height=700, bg="#06040b", highlightthickness=0, bd=0)
canvas.pack()
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(clock[0]))
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={aid: Avatar(a, 800, 600, 0, None, spring_mode=True) for aid, a in agents.items()},
    _chat_directory=lambda: data, scanner=SimpleNamespace(get_agents=lambda: agents),
    dungeon=SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True), _session_rooms=model)
book = PlaceBook(app, path=None)
app.places = book
for aid in agents:
    book._actors[aid] = Place(aid, INSIDE, "new", None)
hall = inside_roster.hall(book)
hall._talk = lambda: []
hall._rooms = lambda: ([], [])
root.update()
canvas._rooms_painter.paint(canvas)


def tick(n: int = 4) -> None:
    for _ in range(n):
        clock[0] += 0.05
        book._now = clock[0]
        book.draw_inside()
    root.update()


tick()
plaques = door_plaque.plaques_for(book)
plaques._read = StoreThrottle(0.0)
tick()
calls = {"show": 0, "leave": 0}
show, leave = plaques.show, plaques.leave


def counted_show(*args) -> None:
    calls["show"] += 1
    if calls["show"] > 20:
        print(f"FAIL show loops {calls}", flush=True)
        os._exit(1)
    show(*args)


def counted_leave(*args) -> None:
    calls["leave"] += 1
    leave(*args)


plaques.show, plaques.leave = counted_show, counted_leave
for item in plaques._items.values():
    canvas.delete(item)
plaques._items.clear()
tick()
x0, y0, x1, y1 = canvas.bbox(plaques._items["glass-orchard"])
canvas.event_generate("<Motion>", x=(x0 + x1) // 2, y=y1 + 1)
root.update()
check("edge shows", plaques._tip is not None and plaques._tip[0] == "glass-orchard", str(plaques._tip))
beats = []
for _ in range(10):
    root.after(1, lambda: beats.append(1))
    tick(1)
check("loop ticks", len(beats) == 10, str(beats))
check("show once", calls == {"show": 1, "leave": 0}, str(calls))
