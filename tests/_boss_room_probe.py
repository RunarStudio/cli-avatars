"""Child process for ``test_boss_room_desktop``: the Oni Pit and the Crypt on an off-screen Dungeon floor, on
made-up data. Exit 77 without a display.

    python tests/_boss_room_probe.py <repo root> <data dir>

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
from cli_avatars.app import boss_dust, boss_rooms, boss_view, crypt_view, cues, inside_roster  # noqa: E402
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


load_sprites(REGISTRY)
played: list[str] = []
cues.play = lambda _app, name: played.append(name)
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
clock = [time.time() + 86400]
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


def size(name: str) -> tuple[int, int]:
    floor = hall.plan().floor(name)
    return (floor.w, floor.h) if floor else (0, 0)


view, crypt, dust = boss_view.view_for(book), crypt_view.view_for(book), boss_dust.dust_for(book)
tick(0.3)
check("oni pit and crypt on the floor", size(boss_rooms.PIT) == (4, 4) and size(boss_rooms.CRYPT) == (4, 4),
      str((size(boss_rooms.PIT), size(boss_rooms.CRYPT))))
check("no backlog: bare pit, empty crypt", "oni" not in view._items and not crypt.rows
      and not [n for n in crypt._items if n.startswith("s:")])
spots = boss_rooms.niches(boss_rooms.room(canvas._rooms_painter.layout, boss_rooms.CRYPT_KIND))
check("niches line the crypt walls", len(spots) >= 2 and sum(n.startswith("n") for n in crypt._items) == len(spots),
      str(len(spots)))

reg = Registry(DATA)
set_topic(DATA, "moon-forge", title="moon-forge", project="lantern", status="open")
cards = [reg.task_create("lantern", f"Moon lantern wick {n}", topic="moon-forge") for n in range(3)]
for card in cards:
    reg.task_move(card["id"], "blocked")
played.clear()
view.reread()
seen, puffs, drawn = [], 0, 0
for _ in range(20):
    tick(0.05)
    seen.append(size(boss_rooms.PIT))
    puffs, drawn = max(puffs, len(dust.puffs)), max(drawn, len(canvas.find_withtag(boss_dust.TAG)))
check("the pit grows a tile a step", seen[-1] == (6, 5) and (5, 5) in seen, str(seen))
check("dust along the moving walls", puffs > 0 and drawn == puffs, str((puffs, drawn)))
check("grind as the walls slide", "grind" in played, str(played))
check("the oni sits in the pit", "oni" in view._items and view._keys["pit"][1] == boss_view.pit_width(hall.plan()))

played.clear()
clock[0] += 31 * 86400
view.reread()
tick(0.1)
check("forgotten cards drop in as skulls", len(crypt.rows) == 3 and len(crypt.born) == 3, str(crypt.rows))
check("rattle on a new skull", "rattle" in played, str(played))
tick(0.8)
check("each skull in its niche", sorted(crypt.slots.values()) == [0, 1, 2]
      and all(canvas.find_withtag(crypt._items[f"s:{c['id']}"]) for c in cards))
check("the crypt grows with the count", size(boss_rooms.CRYPT) == (5, 5), str(size(boss_rooms.CRYPT)))
check("the plaque counts them", crypt._keys["plaque"][1] == 3, str(crypt._keys.get("plaque")))

crypt._hover(cards[1]["id"])
tick(0.1)
texts = " ".join(canvas.itemcget(i, "text") for i in crypt._label if canvas.type(i) == "text")
check("hover shows title and days forgotten", "Moon lantern wick 1" in texts and "Forgotten 3" in texts, texts)
crypt._hover(None, cards[1]["id"])
tick(0.1)
check("leaving hides it", not crypt._label)
crypt.open_card(cards[2]["id"])
check("click opens the card", shown.get("card") == cards[2]["id"] and shown["center"] == "tasks")

slots = dict(crypt.slots)
reg.task_move(cards[0]["id"], "done")
view.reread()
tick(0.3)
check("a done card's skull leaves", cards[0]["id"] not in crypt.slots and f"s:{cards[0]['id']}" not in crypt._items)
check("the others keep their niches", all(crypt.slots[c["id"]] == slots[c["id"]] for c in cards[1:]))

focus.start(DATA, cards[1]["id"])
played.clear()
extra = reg.task_create("lantern", "Moon lantern hook", topic="moon-forge")
view.reread()
tick(0.3)
check("focus holds the rattle of another task", "rattle" not in played and crypt.held == "rattle", str(played))
focus.leave(DATA)
tick(0.1)
check("held rattle plays after focus", "rattle" in played, str(played))

for card in (cards[1], cards[2], extra):
    reg.task_move(card["id"], "done")
view.reread()
for _ in range(80):
    tick(0.1)
    if not view.hits and view.hit is None:
        break
tick(boss_view.DOWN_S + 0.5)
check("cards close: the pit shrinks back", size(boss_rooms.PIT) == (4, 4), str(size(boss_rooms.PIT)))
check("and the crypt empties", size(boss_rooms.CRYPT) == (4, 4) and not crypt.rows)
check("HP 0: bare room, no oni", "oni" not in view._items and "pit" not in view._items, str(view._keys))
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
