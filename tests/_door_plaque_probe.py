"""Child process for ``test_door_plaque``: the door plaques on an off-screen Dungeon floor. Exit 77 without Tk.

    python tests/_door_plaque_probe.py <repo root> <data dir>

Made-up rooms, sessions and a decision in the given data dir. Prints ``ok <check>``; a failed check exits 1.
"""

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
from decisions import ask_decision  # noqa: E402
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
items = dict(plaques._items)
check("one plaque per room", set(items) == {sr.APOTHECARY, "moon-forge", "glass-orchard"}, str(items))
check("counts", plaques.counts.rooms["moon-forge"]["orchestrators"] == 1
      and plaques.counts.rooms["moon-forge"]["agents"] == 2, str(plaques.counts.rooms))
images = {name: canvas.itemcget(item, "image") for name, item in items.items()}
tick(10)
check("steady", dict(plaques._items) == items
      and {name: canvas.itemcget(item, "image") for name, item in items.items()} == images)
ask_decision(data, agent="claude:e5f6a7b8", room="glass-orchard", question="Oak or ash?", options=["a=oak", "b=ash"])
tick()
check("decision counted", plaques.counts.rooms["glass-orchard"]["decisions"] == 1)
check("in place", plaques._items["glass-orchard"] == items["glass-orchard"]
      and canvas.itemcget(items["glass-orchard"], "image") != images["glass-orchard"]
      and canvas.itemcget(items["moon-forge"], "image") == images["moon-forge"])
x0, y0, x1, y1 = canvas.bbox(items["glass-orchard"])
canvas.event_generate("<Motion>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
root.update()
check("hover shows", plaques._tip is not None and plaques._tip[0] == "glass-orchard"
      and canvas.find_withtag(door_plaque.TIP))
canvas.event_generate("<Motion>", x=2, y=2)
root.update()
check("leave hides", plaques._tip is None and not canvas.find_withtag(door_plaque.TIP))
plaques.pin(canvas, "moon-forge")
tick()
check("click pins", plaques._tip is not None and plaques._tip[0] == "moon-forge")
plaques.pin(canvas, "moon-forge")
check("click unpins", plaques._tip is None)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
check("no sound", played == [], str(played))

from cli_avatars.app import door_counts, door_totals  # noqa: E402

dock = tk.Frame(root)
dock.pack()
below = tk.Label(dock, text="Topics")
below.pack()
app._door_totals = None
strip = door_totals.attach(app, dock, below)
strip._read = StoreThrottle(0.0)
strip.refresh(app)
root.update()
check("totals rows", list(strip.rows) == [door_totals.ALL, "glass-orchard", "lantern", "moon-forge"],
      str(list(strip.rows)))
check("totals above topics", dock.pack_slaves()[0] is strip.frame)
row, image = strip.rows[door_totals.ALL]
shown = image.cget("image")
strip.refresh(app)
root.update()
check("totals steady", strip.rows[door_totals.ALL] == (row, image) and image.cget("image") == shown)
ask_decision(data, agent="claude:a1b2c3d4", room="moon-forge", question="Gold or silver?", options=["a=gold", "b=silver"])
strip.refresh(app)
root.update()
check("totals in place", strip.rows[door_totals.ALL] == (row, image) and image.cget("image") != shown
      and strip.counts.total["decisions"] == 2)
strip.hover(door_totals.ALL)
check("totals hover", "2 decisions wait on you" in strip.caption.cget("text"), strip.caption.cget("text"))
strip.show(door_counts.DoorCounts())
check("project gone", list(strip.rows) == [door_totals.ALL])
