"""Child process for ``test_boss_desktop``: the backlog boss on an off-screen Dungeon floor, on made-up data.
Exit 77 without a display.

    python tests/_boss_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import stat
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

import backlog_boss  # noqa: E402
import focus  # noqa: E402
from cli_avatars.app import boss_view, cues, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

DATA = Path(sys.argv[2])


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def weekday_after(days: int, weekday: int) -> float:
    """Noon on the first ``weekday`` at least ``days`` from now (so cards made now are that old)."""
    day = (datetime.now() + timedelta(days=days)).replace(hour=12, minute=0, second=0, microsecond=0)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.timestamp()


load_sprites(REGISTRY)
played: list[str] = []
cues.play = lambda _app, name: played.append(name)
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
clock = [weekday_after(8, 2)]
wednesday = clock[0]
canvas = tk.Canvas(root, width=1200, height=760, highlightthickness=0, bd=0)
canvas.pack()
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(clock[0]))
shown = {"center": "dungeon"}
dungeon = SimpleNamespace(scene=canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _center="dungeon",
                          show_center=lambda name: shown.update(center=name))
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
    places=None, _inside={}, _chat_directory=lambda: DATA, scanner=SimpleNamespace(get_agents=lambda: {}),
    dungeon=dungeon, _session_rooms=model, _tasks_panel=SimpleNamespace(open_card=lambda cid: shown.update(card=cid)))
book = PlaceBook(app, path=None)
app.places = book
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
        root.update_idletasks()


view = boss_view.view_for(book)


def reread() -> None:
    view.reread()


tick(0.3)
plan = hall.plan()
check("pit in the oni pit", boss_view.pit_room(plan) == "Oni Pit", str([f.name for f in plan.floors]))
check("bare room at HP 0", "pit" not in view._items and "oni" not in view._items, str(view._keys))
check("quiet midweek: no bar, no chart", "bar" not in view._items and "chart" not in view._items)

reg = Registry(DATA)
set_topic(DATA, "moon-forge", title="moon-forge", project="lantern", status="open")
cards = [reg.task_create("lantern", f"Moon lantern part {n}", topic="moon-forge") for n in range(7)]
for card in cards[:3]:
    reg.task_move(card["id"], "blocked")
reread()
tick(0.2)
check("blocked and stale cards feed it", view.state["hp"] == 7 and view.state["stage"] == 1, str(view.state["hp"]))
check("pit and oni drawn", all(n in view._items and canvas.find_withtag(view._items[n]) for n in ("pit", "oni")))
check("grows a stage and roars", view._keys["oni"][1] == 1 and "roar" in played, str(played))
image = canvas.itemcget(view._items["oni"], "image")
tick(0.5)
check("idle breathing frames change in place", canvas.itemcget(view._items["oni"], "image") != image)

view._hover(True)
tick(0.1)
texts = " ".join(canvas.itemcget(i, "text") for i in view._text)
check("hover shows HP and the feeding tasks", "HP 7" in texts and "Moon lantern part 0" in texts
      and "blocked" in texts and "idle" in texts, texts)
check("hover shows the bar", "bar" in view._items)
view._hover(False)
view._click("oni")
tick(0.1)
rows = [i for i in view._text if canvas.tag_bind(i, "<Button-1>")]
check("click lists them, rows open", view.listing and len(rows) == 7, str(len(rows)))
view.open_card(cards[0]["id"])
check("a row opens its card", shown.get("card") == cards[0]["id"] and shown["center"] == "tasks")
tick(0.1)
check("list closes", not view.listing and not canvas.find_withtag("boss-list"))

played.clear()
reg.task_move(cards[0]["id"], "done")
reread()
tick(0.1)
check("a close plays a hit", view.hit is not None and view.hit[0]["card"] == cards[0]["id"])
check("thud cue on the hit", played == ["thud"], str(played))
check("hit flash", view._keys["oni"][0] == "flash", str(view._keys.get("oni")))
check("damage number rises", "dmg" in view._items)
check("bar shows the drop", "bar" in view._items and view._keys["bar"][1] == 7, str(view._keys.get("bar")))
xs = set()
for _ in range(6):
    tick(0.05)
    xs.add(canvas.coords(view._items["oni"])[0])
check("shake", len(xs) > 1, str(xs))
tick(boss_view.HIT_S)
check("HP drops", view.hit is None and view.shown_hp == 6 and view._keys["bar"][1] == 6, str(view.shown_hp))
reread()
tick(0.3)
check("one hit per close", played == ["thud"], str(played))

canvas.focus_force()
root.update()
canvas.event_generate("<KeyPress-b>")
root.update()
tick(0.1)
check("b key shows the burn-down", "chart" in view._items and view._keys["chart"][1][2] == 6,
      str(view._keys.get("chart")))
view._click("chart")
tick(0.1)
check("scroll button hides it", "chart" not in view._items)

focus.start(DATA, cards[1]["id"])
played.clear()
reg.task_move(cards[2]["id"], "done")
reread()
tick(boss_view.HIT_S + 0.2)
check("focus holds the cue of another task", played == [], str(played))
focus.leave(DATA)
tick(0.1)
check("held cue plays after focus", played == ["thud"], str(played))

clock[0] = wednesday + 2 * 86400 + 3600
reread()
tick(0.2)
check("friday shows the bar and the chart", view.state["friday"] and "bar" in view._items and "chart" in view._items)

played.clear()
for card in cards[1:]:
    if card["id"] != cards[2]["id"]:
        reg.task_move(card["id"], "done")
reread()
for _ in range(80):
    tick(0.1)
    if not view.hits and view.hit is None:
        break
tick(0.2)
check("last hit plays the fanfare", played[-1:] == ["fanfare"] and played.count("thud") == 4, str(played))
check("defeated", view._keys["oni"][0] == "down" and view.state["defeated"])
mode = stat.S_IMODE((DATA / backlog_boss.STORE_NAME).stat().st_mode)
check("store is owner-only", os.name != "posix" or mode == 0o600, oct(mode))
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
time.sleep(0)
