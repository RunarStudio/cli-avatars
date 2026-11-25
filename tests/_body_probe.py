"""Child process for ``test_body_desktop``: body language on an off-screen Dungeon floor, on made-up data.
Exit 77 without a display.

    python tests/_body_probe.py <repo root> <data dir>

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
from cli_avatars.app import body_spots, body_view, cues, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.body import SLUMP, STRIDE, TAP  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

DATA = Path(sys.argv[2])
ROOMS = (("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE), ("ember-ledger", sr.SIMPLE))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge"), ("e5f6a7b8", "Vessa", "glass-orchard"),
          ("c9d0e1f2", "Pell", "ember-ledger"))


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
for aid, _name, topic in AGENTS:
    join_topic(DATA, topic, aid)

clock = [time.time()]
agents = {aid: AgentInfo(aid, name, status="idle", skin="caine", source="claude", project=room,
                         last_seen=clock[0] - 600) for aid, name, room in AGENTS}
canvas = tk.Canvas(root, width=1200, height=760, highlightthickness=0, bd=0)
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
    body_view.view_for(book)._read._ready = False


def near(a, b, tol=0.05) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


tick(0.5)
view = body_view.view_for(book)
check("idle by default", set(view.found.poses.values()) == {"idle"}, str(view.found.poses))
check("benches by the rooms", {"moon-forge", "glass-orchard", "ember-ledger"} <= set(view.benches), str(view.benches))
check("bench items on the floor", len(canvas.find_withtag(body_view.PROP)) >= 3)
check("no smoke yet", not canvas.find_withtag(body_view.SMOKE))

agents["a1b2c3d4"].status = "busy"
tick(1.0)
check("flowing strides", view.found.poses["a1b2c3d4"] == STRIDE)
orrin = app._inside["a1b2c3d4"]
check("stride frame drawn", getattr(orrin, "_body_sig", (None,))[0] == STRIDE, str(getattr(orrin, "_body_sig", None)))
check("stride paces with a short pause", body_view.PAUSE[STRIDE] < 0.5)

reg = Registry(DATA)
card = reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
reg.task_move(card["id"], "doing")
reg.task_move(card["id"], "blocked")
reread()
tick(0.2)
check("blocked card slumps", view.found.poses["e5f6a7b8"] == SLUMP, str(view.found.poses))
check("sigh cue", "sigh" in played, str(played))
seat = view.targets["e5f6a7b8"][1]
check("walks with a trip through the doors", "e5f6a7b8" in hall._trips)
tick(12.0)
check("sits on the bench", near(hall._feet["e5f6a7b8"], seat), f"{hall._feet['e5f6a7b8']} {seat}")
corner = view.benches["glass-orchard"][0]
check("seat on its room's bench", abs(seat[1] - (corner[1] + 0.32)) < 1e-6 and corner[0] < seat[0] < corner[0] + 2)
check("not sent to the user", not hall.walker.marked("e5f6a7b8"))
vessa = app._inside["e5f6a7b8"]
check("slump frame drawn", getattr(vessa, "_body_sig", (None,))[0] == SLUMP)

held = focus.start(DATA, card["id"]) and focus.current(DATA) is not None
played.clear()
ask_decision(DATA, agent="c9d0e1f2", room="ember-ledger", question="Copper or silver trim?",
             options=["a=Copper", "b=Silver"])
reread()
tick(0.2)
check("open decision taps", view.found.poses["c9d0e1f2"] == TAP, str(view.found.poses))
check("held in focus", held and "knock" not in played, f"{held} {played}")
focus.leave(DATA)
tick(13.0)
door = view.targets["c9d0e1f2"][1]
check("waits at the door", near(hall._feet["c9d0e1f2"], door), f"{hall._feet['c9d0e1f2']} {door}")
layout = canvas._rooms_painter.layout
room = next(r for r in layout["rooms"] if r.get("name") == "ember-ledger")
plan = hall.plan()
check("door spot inside its room", plan.floor("ember-ledger").holds(*door))
check("door spot on the way to the user", body_spots.door(plan, "ember-ledger", hall.room_of(inside_roster.USER_ID),
                                                          0, room)[0] == door)
check("tap frame drawn", getattr(app._inside["c9d0e1f2"], "_body_sig", (None,))[0] == TAP)

played.clear()
view.runs._start["a1b2c3d4"] = clock[0] - 21 * 60
tick(1.5)
check("long run smokes", view.found.smoke.get("moon-forge", 0) > 0, str(view.found.smoke))
check("smoke items drawn", bool(canvas.find_withtag(body_view.SMOKE)))
check("crackle cue", "crackle" in played, str(played))
thin = view.found.smoke["moon-forge"]
view.runs._start["a1b2c3d4"] = clock[0] - 70 * 60
tick(0.5)
check("thicker with time", view.found.smoke["moon-forge"] > thin)
images = {canvas.itemcget(i, "image") for i in canvas.find_withtag(body_view.SMOKE)}
tick(0.4)
check("smoke drifts in place", {canvas.itemcget(i, "image") for i in canvas.find_withtag(body_view.SMOKE)} != images)
count = len(canvas.find_all())
tick(0.5)
check("items changed in place", len(canvas.find_all()) == count, f"{count} {len(canvas.find_all())}")

view._motion(canvas, vessa.x + vessa.aw / 2, vessa.y + vessa.ah / 2)
tick(0.1)
check("hover shows the word", view._keys.get("hover", (None, None))[1] == "STUCK", str(view._keys.get("hover")))
view._motion(canvas, -5, -5)
tick(0.1)
check("hover leaves", "hover" not in view._items)

rows = hall.snapshot[1] if hall.snapshot else []
by = {r["id"]: r for r in rows}
check("phone rows carry the pose", by.get("e5f6a7b8", {}).get("pose") == SLUMP, str(by.get("e5f6a7b8")))
check("phone rows carry the smoke", by.get("a1b2c3d4", {}).get("smoke", 0) > 0)

reg.task_move(card["id"], "doing")
reread()
tick(0.3)
check("cleared stands up", view.found.poses["e5f6a7b8"] != SLUMP and "e5f6a7b8" not in view.targets)
check("walks back home", "e5f6a7b8" in hall._trips)

(DATA / "config.json").write_text(json.dumps({"body": {"enabled": False}}), encoding="utf-8")
reread()
tick(0.3)
check("off in config", view.found.poses == {} and not view.targets)
reg.task_move(card["id"], "blocked")
reread()
tick(0.3)
check("needs walk back when off", hall.walker.marked("e5f6a7b8") and "e5f6a7b8" not in view.targets)
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
