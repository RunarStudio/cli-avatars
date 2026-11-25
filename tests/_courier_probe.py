"""Child process for ``test_courier_desktop``: the courier on an off-screen Dungeon floor, on made-up data.
Exit 77 without a display.

    python tests/_courier_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

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
import messenger  # noqa: E402
import needs_you  # noqa: E402
from cli_avatars.app import courier_view, cues, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
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
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge"), ("e5f6a7b8", "Vessa", "glass-orchard"))


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
shown = {"center": "dungeon"}
dungeon = SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _center="dungeon",
                          show_center=lambda name: shown.update(center=name))
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in agents.items()},
    _chat_directory=lambda: DATA, scanner=SimpleNamespace(get_agents=lambda: agents), dungeon=dungeon,
    _session_rooms=model)
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
        book.draw_inside()


def reread() -> None:
    courier_view.view_for(book).reread()


reg = Registry(DATA)
forge = reg.task_create("lantern", "Forge the moon lantern", topic="moon-forge")
orchard = reg.task_create("lantern", "Glass apple orchard", topic="glass-orchard")
ledger = reg.task_create("lantern", "Ember ledger export", topic="ember-ledger")
tick(0.3)
view = courier_view.view_for(book)
check("quiet without a decision", view.walk is None and not canvas.find_withtag(courier_view.TAG))
check("nothing stored without a link", not (DATA / messenger.STORE_NAME).exists())

row = ask_decision(DATA, agent="a1b2c3d4", room="moon-forge", question="Silver or gold rims?",
                   options=["a=Silver", "b=Gold"], card=forge["id"])
reg.decision_answer(row["id"], choice="a", text="affects Glass apple orchard")
reread()
tick(0.1)
check("a courier leaves the deciding room", view.walk is not None and view.walk.info["from_room"] == "moon-forge",
      str(view.walk and view.walk.info))
check("bound for the affected room", view.walk.info["to_room"] == "glass-orchard")
check("rustle cue on leave", "rustle" in played, str(played))
plan = hall.plan()
check("walks through the doors", plan.room_at(*view.walk.path[0]) == "moon-forge"
      and plan.room_at(*view.walk.path[-1]) == "glass-orchard" and len(view.walk.path) > 2)
walker = view._items.get("walker")
check("courier drawn on the floor", walker is not None and bool(canvas.find_withtag(walker)))
first = view.walk.feet()[0]
tick(0.5)
mid = view.walk.feet()[0]
check("eased start", 0 < view.walk.done < 0.5 and courier_view.ease(0.1) < 0.1, str(view.walk.done))
check("moves along the path", mid != first)
hall.snapshot = None
tick(0.05)
rows = hall.snapshot[1] if hall.snapshot else []
check("phone row for the walk", any(r["kind"] == "courier" and r["walk"] for r in rows), str(rows[-1:]))
image = canvas.itemcget(walker, "image")
tick(0.2)
check("walk frames change in place", view._items.get("walker") == walker and canvas.itemcget(walker, "image") != image)

b = ask_decision(DATA, agent="a1b2c3d4", room="moon-forge", question="Does Ember ledger export carry rims?",
                 options=["a=Yes", "b=No"], card=forge["id"])
reg.decision_answer(b["id"], choice="a")
reread()
tick(0.1)
check("a second courier queues", len(view.queued) == 1 and view.walk.info["to"] == orchard["id"], str(view.queued))
check("queue pip on the walker", "pip" in view._items)

played.clear()
for _ in range(400):
    tick(0.1)
    if view.walk is None:
        break
check("arrives", view.walk is None and messenger.load(DATA)[f"{row['id'][:8]}-{orchard['id'][:8]}"]["state"]
      == messenger.ARRIVED)
check("seal flash on arrival", any(n.startswith("flash") for n in view._items), str(list(view._items)))
check("stamp cue on arrival", "stamp" in played, str(played))
reread()
tick(0.1)
check("the affected card lights up", orchard["id"] in view.lit and f"card:{orchard['id']}" in view._items)
check("ribbon says where from", view._keys[f"ribbon:{orchard['id']}"][1] == "new from moon-forge",
      str(view._keys.get(f"ribbon:{orchard['id']}")))
check("never piles: the next waits its turn", view.walk is None or view.walk.done < 0.2)
tick(courier_view.GAP_S + 0.2)
check("the queued one leaves after", view.walk is not None and view.walk.info["to"] == ledger["id"])

reg.task_move(orchard["id"], "doing")
reg.task_move(orchard["id"], "blocked")
check("needs-you row while the card waits", any(r["kind"] == "courier" and r["card"] == orchard["id"]
                                                for r in needs_you.pending(DATA)))

boxes = {orchard["id"]: tk.Frame(root, highlightthickness=1, highlightbackground="#8a6a3a")}
tk.Label(boxes[orchard["id"]], text="Glass apple orchard").pack()
app._tasks_panel = SimpleNamespace(cards=boxes, open_card=lambda cid: shown.update(card=cid))
tick(0.1)
ribbon = getattr(boxes[orchard["id"]], "courier_ribbon", None)
check("tasks tile glows with the ribbon", ribbon is not None and boxes[orchard["id"]].cget("highlightthickness") == 2
      and "MOON-FORGE" in ribbon.cget("text"))

shown["center"] = "tasks"
dungeon._center = "tasks"
view._click(f"ribbon:{orchard['id']}")
tick(0.1)
check("click opens the note on the floor", view.note is not None and shown["center"] == "dungeon")
texts = " ".join(canvas.itemcget(i, "text") for i in view._text)
check("note shows the decision and the reason", "Silver or gold rims?" in texts and "Silver" in texts
      and "affects" in texts, texts)
check("opened stops the glow", orchard["id"] not in view.lit
      and messenger.load(DATA)[f"{row['id'][:8]}-{orchard['id'][:8]}"]["state"] == messenger.OPENED)
reread()
tick(0.2)
check("card and ribbon gone", f"card:{orchard['id']}" not in view._items and boxes[orchard["id"]].courier_ribbon is None)
view.open_task()
check("open task from the note", shown.get("card") == orchard["id"] and shown["center"] == "tasks")
tick(0.1)
check("note closes", view.note is None and not canvas.find_withtag("courier-note"))

focus.start(DATA, forge["id"])
c = ask_decision(DATA, agent="e5f6a7b8", room="glass-orchard", question="Pick a glass tint for Ember ledger export?",
                 options=["a=Amber", "b=Clear"], card=orchard["id"])
reg.decision_answer(c["id"], choice="b")
for _ in range(400):
    tick(0.1)
    if view.walk is None:
        break
played.clear()
reread()
tick(1.5)
check("focus holds a courier of another task", view.walk is None and view.queued
      and view.queued[0]["to"] == ledger["id"], str(view.walk and view.walk.info))
check("its cues wait", not played, str(played))
focus.leave(DATA)
reread()
tick(0.3)
check("released after focus", view.walk is not None and "rustle" in played, str(played))
check("no new toplevel", len(root.winfo_children()) == tops_before + 1)
root.destroy()
