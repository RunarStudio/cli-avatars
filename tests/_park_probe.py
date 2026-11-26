"""Child process for ``test_park_desktop``: the park, idle objects and task routing on an off-screen Dungeon floor,
on made-up data. Exit 77 without a display.

    python tests/_park_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
from cli_avatars.app import cues, idle_life, inside_roster, life_view, park, task_sessions  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

DATA = Path(sys.argv[2])
ROOMS = (("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE), ("ember-ledger", sr.SIMPLE))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge"), ("e5f6a7b8", "Vessa", "glass-orchard"),
          ("c9d0e1f2", "Pell", "ember-ledger"))
SID = "c9d0e1f2-0000-4000-8000-00000000abcd"


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


load_sprites(REGISTRY)
played: list[str] = []
cues.play = lambda _app, name: played.append(name)
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
for topic, kind in ROOMS:
    model.open(kind, "claude", topic)
    set_topic(DATA, topic, title=topic, project="lantern", status="open")

clock = [time.time()]
agents = {aid: AgentInfo(aid, name, status="busy", skin="caine", source="claude", project=room,
                         last_seen=clock[0]) for aid, name, room in AGENTS}
canvas = tk.Canvas(root, width=1366, height=800, highlightthickness=0, bd=0)
canvas.pack()
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(clock[0]))
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in agents.items()},
    _chat_directory=lambda: DATA, scanner=SimpleNamespace(get_agents=lambda: agents),
    dungeon=SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True), _session_rooms=model)
book = PlaceBook(app, path=None)
app.places = book
for aid in agents:
    book._actors[aid] = Place(aid, INSIDE, "new", None)
hall = inside_roster.hall(book)
hall._talk = lambda: []
root.update()
canvas._rooms_painter.paint(canvas)
tops_before = len(root.winfo_children())


def tick(seconds: float, step: float = 0.05) -> None:
    for _ in range(max(1, round(seconds / step))):
        clock[0] += step
        book._now = clock[0]
        for agent in agents.values():
            if agent.status == "busy":
                agent.last_seen = clock[0]
        book.draw_inside()


def reread() -> None:
    hall._read._ready = False
    view = life_view.view_for(book)
    view._read._ready = False
    view._config._ready = False


def near(a, b, tol=0.08) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def room_at(aid: str) -> str | None:
    return hall.plan().room_at(*hall._feet[aid])


tick(0.5)
plan = hall.plan()
check("park on the floor", plan.floor(park.NAME) is not None and bool(plan._hops(sr.APOTHECARY, park.NAME)))
view = life_view.view_for(book)
check("busy avatars stay home", not view.holds, str(view.holds))
check("park drawn", bool(canvas.find_withtag(life_view.FX)))
check("idle objects drawn", len(canvas.find_withtag(life_view.PROP)) >= 5, str(len(canvas.find_withtag(life_view.PROP))))
check("task tables drawn", len(canvas.find_withtag(life_view.TABLE)) >= 3)

agents["a1b2c3d4"].status = "idle"
agents["a1b2c3d4"].last_seen = clock[0] - 90
tick(0.3)
hold = view.holds.get("a1b2c3d4")
check("short idle takes an object", hold is not None and hold.tier == idle_life.SHORT, str(view.holds))
check("walks there through the doors", "a1b2c3d4" in hall._trips)
tick(14.0)
check("stands at it", near(hall._feet["a1b2c3d4"], view.holds["a1b2c3d4"].feet),
      f"{hall._feet['a1b2c3d4']} {view.holds['a1b2c3d4'].feet}")
check("object reserved", view.life.taken()[hold.oid] == ["a1b2c3d4"])
check("in use loop drawn", any(k[1] for k in view._keys.values() if k and k[0] == "prop"), str(view._keys))

played.clear()
agents["e5f6a7b8"].status = "idle"
agents["e5f6a7b8"].last_seen = clock[0] - 700
tick(0.3)
check("long idle goes to the park", view.holds["e5f6a7b8"].room == park.NAME, str(view.holds.get("e5f6a7b8")))
tick(18.0)
check("reaches the park", room_at("e5f6a7b8") == park.NAME, str(hall._feet["e5f6a7b8"]))
rows = {r["id"]: r for r in (hall.snapshot[1] if hall.snapshot else [])}
check("phone rows carry the idle act", rows.get("e5f6a7b8", {}).get("idle", {}).get("act") in
      {"sit", "hit", "lift", "spar", "stroll"}, str(rows.get("e5f6a7b8")))
check("park ambience", "night" in played, str(played))

agents["e5f6a7b8"].status = "busy"
tick(0.3)
check("busy releases the spot", "e5f6a7b8" not in view.holds)
check("walks back", "e5f6a7b8" in hall._trips)
tick(20.0)
check("back in its room", room_at("e5f6a7b8") == "glass-orchard", str(room_at("e5f6a7b8")))

reg = Registry(DATA)
card = reg.task_create("lantern", "Count the glass apples", topic="ember-ledger", assignee="a1b2c3d4")
reg.task_move(card["id"], "doing")
agents["a1b2c3d4"].status = "busy"
reread()
tick(0.3)
check("assigning walks it to the card's room", hall.room_of("a1b2c3d4") == "ember-ledger", hall.room_of("a1b2c3d4"))
tick(20.0)
check("arrives in the card's room", room_at("a1b2c3d4") == "ember-ledger", str(room_at("a1b2c3d4")))
seat = view.targets.get("a1b2c3d4")
check("works at the table", seat is not None and near(hall._feet["a1b2c3d4"], seat[1]), str(seat))

other = reg.task_create("lantern", "Weigh the moon", topic="glass-orchard")
_card, chat = task_chats.start_chat(reg, other["id"], "claude")
task_sessions.remember(DATA, chat["room"], "claude", SID)
reread()
tick(0.3)
check("a task chat walks its session to the card's room", hall.room_of("c9d0e1f2") == "glass-orchard",
      hall.room_of("c9d0e1f2"))

reg.task_move(card["id"], "done")
reread()
tick(0.3)
check("done sends it home", hall.room_of("a1b2c3d4") == "moon-forge", hall.room_of("a1b2c3d4"))

played.clear()
agents["e5f6a7b8"].status = "idle"
agents["e5f6a7b8"].last_seen = clock[0] - 900
focus.start(DATA, other["id"])
reread()
tick(18.0)
check("held in focus", "train" not in played and "night" not in played, str(played))
focus.leave(DATA)

(DATA / "config.json").write_text(json.dumps({"park": {"enabled": False}}), encoding="utf-8")
reread()
tick(3.0)
check("park off in config", hall.plan().floor(park.NAME) is None)
check("long idle falls back to an object", view.holds.get("e5f6a7b8") is not None
      and view.holds["e5f6a7b8"].tier == idle_life.SHORT, str(view.holds.get("e5f6a7b8")))
(DATA / "config.json").write_text(json.dumps({"idle_props": {"enabled": False}, "park": {"enabled": False}}),
                                  encoding="utf-8")
reread()
tick(1.0)
check("idle objects off in config", not view.holds and not canvas.find_withtag(life_view.PROP), str(view.holds))
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
