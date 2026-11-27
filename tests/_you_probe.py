"""Child process for ``test_you_desktop``: the keeper and the needs-you bubbles on an off-screen Dungeon floor.
Made-up data; exit 77 without a display.

    python tests/_you_probe.py <repo root> <data dir>

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
from cli_avatars.app import body_view, cues, dungeon_nav, inside_roster, needs_panel, you_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.body import TAP  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from routing import PointerGesture  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA = Path(sys.argv[2])
AGENTS = (("a1b2c3d4", "Orrin"), ("e5f6a7b8", "Vessa"))


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


load_sprites(REGISTRY)
played: list[str] = []
cues.play = lambda _app, name: played.append(name)
opened: list = []
needs_panel.open_item = lambda _app, item: opened.append(item["key"])
(DATA / "config.json").write_text('{"park": {"enabled": false}, "idle_props": {"enabled": false}}', encoding="utf-8")
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
model.open(sr.MAIN, "claude", "moon-forge")
model.open(sr.SIMPLE, "claude", "glass-orchard")

# off Fridays: the boss burn-down parchment covers the Apothecary floor that day
clock = [time.time() - (86400 if time.localtime().tm_wday == 4 else 0)]
agents = {aid: AgentInfo(aid, name, status="idle", skin="caine", source="claude", project="lantern",
                         last_seen=clock[0] - 600) for aid, name in AGENTS}
canvas = tk.Canvas(root, width=1200, height=760, highlightthickness=0, bd=0)
canvas.pack()
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(clock[0]))
dungeon = SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _schedule_save=lambda: None)
chats: list = []
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in agents.items()},
    _chat_directory=lambda: DATA, scanner=SimpleNamespace(get_agents=lambda: agents), dungeon=dungeon,
    _session_rooms=model, _gesture=PointerGesture(), _nav=None, _grabbed=None, _open_chat_for_avatar=lambda av: chats.append(av.agent.agent_id))
dungeon.app = app
book = PlaceBook(app, path=None)
app.places = book
for aid in agents:
    book._actors[aid] = Place(aid, INSIDE, "new", None)
hall = inside_roster.hall(book)
hall._talk = lambda: []
root.update()
dungeon_nav.attach(dungeon)
canvas._rooms_painter.paint(canvas)
tops_before = len(root.winfo_children())


def tick(seconds: float, step: float = 0.05) -> None:
    for _ in range(max(1, round(seconds / step))):
        clock[0] += step
        book._now = clock[0]
        book.draw_inside()


def reread() -> None:
    hall._read._ready = False
    body_view.view_for(book)._read._ready = False
    you_view.view_for(book)._read._ready = False


def key(sym: str, up: bool = False):
    event = SimpleNamespace(keysym=sym)
    return you_view.key_up(app, event) if up else dungeon_nav.on_key(dungeon, event)


tick(0.5)
view = you_view.view_for(book)
check("keeper starts in the throne room", view.room == "moon-forge", str(view.room))
check("keeper drawn", len(canvas.find_withtag(you_view.TAG)) >= 1)
check("no bubbles while nothing waits", not canvas.find_withtag(you_view.BUBBLE))
check("no badge while nothing waits", "badge" not in view._items)

# click the floor of the other room: the keeper walks there through the doors and the camera follows
plan = hall.plan()
target = plan.floor("glass-orchard").centre()
x, y = canvas._rooms_painter.to_canvas(*target)
pan0 = canvas._camera.pan
pointer = InputController(app)
press = SimpleNamespace(x=x, y=y, x_root=x, y_root=y)
pointer.on_scene_press(press)
pointer.on_scene_release(press)
check("floor click walks", USER_ID in hall._trips)
trip = hall._trips.get(USER_ID)
check("walk is a trip through the doors", trip is not None and len(trip[0]) > 2, str(trip and trip[0]))
tick(0.6)
check("camera follows the walk", canvas._camera.pan != pan0, str(canvas._camera.pan))
tick(12.0)
feet = hall._feet[USER_ID]
check("arrives in the clicked room", plan.room_at(*feet) == "glass-orchard", str(feet))
check("room saved for the next start", json.loads((DATA / "ui" / "you_avatar.json").read_text())["room"]
      == "glass-orchard")

# keys pan the camera until the keeper is selected
pan1 = canvas._camera.pan
key("Left")
check("keys pan while not selected", canvas._camera.pan != pan1 and hall._feet[USER_ID] == feet)
bx0, by0, bx1, by1 = view._box
check("click on the keeper selects it", you_view.click(app, SimpleNamespace(x=(bx0 + bx1) / 2, y=(by0 + by1) / 2))
      and view.selected)
tick(0.1)
check("selection ring drawn", "ring" in view._items)
pan2 = canvas._camera.pan
check("selected keeper takes the key", key("d") == "break")
tick(0.5)
moved = hall._feet[USER_ID]
check("held key walks it", moved[0] > feet[0] and moved[1] < feet[1], f"{feet} -> {moved}")
check("faces the way it walks", view.face == 1)
key("d", up=True)
tick(0.8)
still = hall._feet[USER_ID]
tick(0.3)
check("release stops", hall._feet[USER_ID] == still)
for _ in range(60):
    key("Up")
    tick(0.1)
check("walls stop the keys", plan.walkable(*hall._feet[USER_ID]))
check("Esc lets go", key("Escape") == "break" and not view.selected)
check("keys pan again after Esc", key("Up") == "break" and canvas._camera.pan != pan2)

# a decision for Vessa: no topic member, still a bubble, a tap pose and the badge
ask_decision(DATA, agent="e5f6a7b8", room="lantern", question="Copper or silver trim?", options=["a=Copper", "b=Silver"])
reread()
tick(2.2)
check("decision reaches its asker", view.needs.get("e5f6a7b8") is not None and view.needs["e5f6a7b8"].kind == "decision",
      str(view.needs))
check("bubble over the asker", "bubble:e5f6a7b8" in view._items)
check("badge counts it", "badge" in view._items and view._keys["badge"][1] == 1)
check("asker taps without hook status", body_view.view_for(book).found.poses.get("e5f6a7b8") == TAP,
      str(body_view.view_for(book).found.poses))
check("no extra cue for a row", "arrive" not in played, str(played))
heights = set()
for _ in range(8):
    heights.add(canvas.coords(view._items["bubble:e5f6a7b8"])[1])
    tick(0.1)
check("bubble bobs", len(heights) > 1, str(heights))
for zoom in (1, 3):
    canvas._camera.zoom = zoom
    tick(0.1)
    bbox = canvas.bbox(view._items["bubble:e5f6a7b8"])
    check(f"bubble readable at zoom {zoom}", bbox is not None and bbox[2] - bbox[0] >= 26, str(bbox))
bx0, by0, bx1, by1 = view._bubbles["e5f6a7b8"]
check("bubble click opens the row", you_view.click(app, SimpleNamespace(x=(bx0 + bx1) / 2, y=(by0 + by1) / 2))
      and opened[-1].startswith("decision:"), str(opened))

# hook status alone: Orrin waits on a reply; the arrive cue plays once, held in focus
played.clear()
agents["a1b2c3d4"].status = "blocked"
tick(1.2)
check("hook blocked bubbles", view.needs.get("a1b2c3d4") is not None and view.needs["a1b2c3d4"].kind == "reply")
check("arrive cue for a new bubble", played.count("arrive") == 1, str(played))
agents["a1b2c3d4"].status = "idle"
tick(1.2)
card = Registry(DATA).task_create("lantern", "Polish the brass")
held_focus = focus.start(DATA, card["id"]) and focus.current(DATA) is not None
reread()
played.clear()
agents["a1b2c3d4"].status = "blocked"
tick(1.2)
check("cue held in focus", held_focus and "arrive" not in played, f"{held_focus} {played}")
check("other tasks' rows wait in focus", "e5f6a7b8" not in view.needs, str(view.needs))
focus.leave(DATA)
reread()
tick(1.2)

# walk up to Orrin: his chat opens once
tick(4.0)
chats.clear()
orrin = hall._feet["a1b2c3d4"]
x, y = canvas._rooms_painter.to_canvas(*orrin)
canvas._camera.move(round(600 - x), round(380 - y))
canvas._rooms_painter.paint(canvas)
x, y = canvas._rooms_painter.to_canvas(orrin[0] + 0.4, orrin[1] + 0.4)
check("walk next to the agent", view.walk_to(x, y))
tick(0.2)
check("not opened before it gets there", chats == [], str(chats))
for _ in range(4):
    for _ in range(30):
        tick(1.0)
        if chats or USER_ID not in hall._trips:
            break
    if chats:
        break
    orrin = hall._feet["a1b2c3d4"]
    x, y = canvas._rooms_painter.to_canvas(orrin[0] + 0.3, orrin[1] + 0.3)
    view.walk_to(x, y)
check("walking up opens the row", chats == ["a1b2c3d4"], str(chats))
tick(1.0)
check("opens once per approach", chats == ["a1b2c3d4"], str(chats))

# phone rows carry the need and the badge
hall.snapshot = None
tick(0.05)
rows = {row["id"]: row for row in hall.snapshot[1]}
check("phone row carries the need", rows["a1b2c3d4"].get("need") == "reply", str(rows["a1b2c3d4"]))
check("phone keeper carries the badge", rows[USER_ID].get("badge") == 2, str(rows[USER_ID]))
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
