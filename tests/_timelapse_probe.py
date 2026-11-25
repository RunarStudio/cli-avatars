"""Child process for ``test_timelapse_desktop``: the time-lapse on an off-screen Dungeon floor, on made-up data.
Exit 77 without a display.

    python tests/_timelapse_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
import time
import uuid
from datetime import date, datetime, timedelta
from datetime import time as dtime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
import timelapse  # noqa: E402
from board.store import LocalStore  # noqa: E402
from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, timelapse_ghosts, timelapse_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import timelapse_art as art  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.room import add_participant  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

DATA = Path(sys.argv[2])
DAY = date.today() - timedelta(days=1)


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def stamp(hour: int, minute: int = 0) -> str:
    local = datetime.combine(DAY, dtime(hour, minute)).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch(hour: int, minute: int = 0) -> float:
    return datetime.combine(DAY, dtime(hour, minute)).timestamp()


set_topic(DATA, "moon-forge", title="Moon forge", project="lantern", status="open")
set_topic(DATA, "glass-orchard", title="Glass orchard", project="lantern", status="open")
reg = Registry(DATA)
gate = reg.task_create("lantern", "Polish the moon gate", topic="moon-forge")["id"]
pear = reg.task_create("lantern", "Blow a glass pear", topic="glass-orchard")["id"]
chat = f"task-{pear[:8]}-1"
reg.store.update(pear, lambda c: ({**c, "chats": [{"id": str(uuid.uuid4()), "cli": "claude",
                                                  "created": stamp(8), "room": chat}]}, []))
store = LocalStore(DATA)
for hour, card, src, dst in ((9, gate, "todo", "doing"), (11, pear, "todo", "doing")):
    store.append_event({"id": str(uuid.uuid4()), "ts": stamp(hour), "card": card, "actor": "daniel",
                        "kind": "moved", "from": src, "to": dst})
for hour, sender, note in ((11, "user", "Blow it thin"), (11, "claude:room", "Blown"), (15, "claude:room", "Cooled")):
    append_channel(DATA, {"ts": epoch(hour, 5), "from": sender, "to": "user" if sender != "user" else "claude:room",
                          "channel": chat, "icon": "speech", "note": note, "kind": "msg"})
add_participant(DATA, chat, "claude")

played = []
cues.play = lambda _app, name: played.append(name)
opened = []
window = ChatWindow(root, directory=DATA, agents=[], config={}, offscreen=True, room_pane=RoomPane)
app = SimpleNamespace(root=root, config={}, _chat_directory=lambda: DATA, _chat_window=window, _inside={},
                      _show_chat=lambda topic_id=None, address_id=None: (opened.append(topic_id),
                                                                         window.open(topic_id=topic_id)))
model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
model.open(sr.SIMPLE, "claude", "moon-forge")
model.open(sr.SIMPLE, "claude", "glass-orchard")
canvas = tk.Canvas(root, width=1366, height=700, highlightthickness=0)
canvas.place(x=0, y=0)
root.geometry("1366x700+0+0")
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(0.0))
root.update()
canvas._rooms_painter.paint(canvas)
before = set(root.winfo_children())
book = SimpleNamespace(app=app, _hall=SimpleNamespace(snapshot=(0.0, [
    {"id": "__you__", "kind": "user", "name": "You", "room": "Apothecary", "feet": (0.0, 0.0)}])))
lapse = timelapse_view.lapse_for(book)

timelapse_view.paint(book, canvas, 1.0)
check("entry plate", bool(canvas.find_withtag(timelapse_view.ENTRY)) and not lapse.on)
check("room log kept", timelapse.log_path(DATA, date.today()).is_file())
box = canvas.bbox(lapse._items["entry"])
check("entry click", lapse.press((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) == "break" and lapse.on)
timelapse_view.paint(book, canvas, 1.1)
check("covers the live floor", {"night", "map", "bar", "glass", "dial", "play", "speed"} <= set(lapse._items),
      str(sorted(lapse._items)))
lapse.go(-1)
check("previous day", lapse.day == DAY and len(lapse.built["frames"]) >= 3, str(lapse.built and lapse.built["frames"]))
check("day starts at its first frame", lapse.minute == 9 * 60, str(lapse.minute))
timelapse_view.paint(book, canvas, 1.2)
plan = Plan.from_layout(canvas._rooms_painter.layout)
feet = timelapse_ghosts.where(lapse.built, plan, "daniel", lapse.minute)
check("ghost in the task's room", feet is not None and plan.room_at(*feet[0]) == "moon-forge" and not feet[2],
      str(feet))
x, y = canvas._rooms_painter.to_canvas(*feet[0])
item = lapse._items["spr:daniel"]
check("ghost drawn there", abs(canvas.coords(item)[0] - x) < 1, f"{canvas.coords(item)} {x}")
items = dict(lapse._items)
lapse.seek(11 * 60 - timelapse.WALK_MIN / 2, tick=False)
timelapse_view.paint(book, canvas, 1.3)
mid = timelapse_ghosts.where(lapse.built, plan, "daniel", lapse.minute)
check("walks between rooms", mid is not None and mid[2] and canvas.coords(lapse._items["spr:daniel"])[0] != x,
      str(mid))
check("in place", all(lapse._items.get(k) == v for k, v in items.items()), f"{items} {lapse._items}")
check("trail motes", any(canvas.itemcget(m, "state") == "normal" for m in lapse._motes))
lapse.seek(12 * 60, tick=False)
timelapse_view.paint(book, canvas, 1.4)
end = timelapse_ghosts.where(lapse.built, plan, "daniel", lapse.minute)
check("arrives", plan.room_at(*end[0]) == "glass-orchard" and not end[2], str(end))
check("map tinted to the hour", lapse._keys["map"][2] == 12, str(lapse._keys["map"]))

x0, y0, width = lapse._bar
played.clear()
lapse.press(x0 + art.track_x(14 * 60, width) * timelapse_view.K, y0 + 26 * timelapse_view.K)
check("scrub with a tick", abs(lapse.minute - 14 * 60) < 3 and played == ["tick"], f"{lapse.minute} {played}")
lapse.drag(x0 + art.track_x(16 * 60, width) * timelapse_view.K, y0)
check("drag scrubs", abs(lapse.minute - 16 * 60) < 3, str(lapse.minute))
lapse._release()

played.clear()
gem = x0 + art.track_x(15 * 60 + 5, width) * timelapse_view.K
check("gem click opens the chat", lapse.press(gem, y0 + 12 * timelapse_view.K) == "break" and opened[-1] == chat,
      str(opened))
root.update()
pane = window._room
lit = pane._term.tag_ranges("moment")
check("chat scrolled to that message", bool(lit) and pane._term.get(lit[0], lit[1]).strip() == "Cooled",
      pane._term.get(lit[0], lit[1]) if lit else "none")
check("moment cue", played == ["moment"], str(played))

lapse.seek(11 * 60 + 10, tick=False)
timelapse_view.paint(book, canvas, 1.5)
sx, sy = canvas.coords(lapse._items["spr:daniel"])
opened.clear()
lapse.press(sx, sy - 10)
root.update()
lit = pane._term.tag_ranges("moment")
check("ghost click opens its chat at that time", opened == [chat] and pane._term.get(lit[0], lit[1]).strip()
      == "> Blow it thin", f"{opened} {pane._term.get(lit[0], lit[1]) if lit else ''}")

lapse.toggle_play()
lapse._clock = time.monotonic() - 0.2
start = lapse.minute
timelapse_view.paint(book, canvas, 1.6)
check("plays forward", lapse.playing and lapse.minute > start, f"{start} {lapse.minute}")
canvas.focus_force()
canvas.event_generate("<KeyPress-space>")
root.update()
check("space pauses", not lapse.playing)

focus.start(DATA, gate)
played.clear()
lapse.seek(lapse.minute + 30)
timelapse_view.open_moment(app, timelapse.moment(lapse.built, 15 * 60))
check("held in focus", focus.current(DATA) == gate and played == [], str(played))
focus.leave(DATA)
timelapse_view.open_moment(app, timelapse.moment(lapse.built, 15 * 60))
check("cue after focus", played == ["moment"], str(played))

canvas.event_generate("<KeyPress-Escape>")
root.update()
timelapse_view.paint(book, canvas, 1.7)
check("esc returns live", not lapse.on and set(lapse._items) == {"entry"}
      and set(canvas.find_withtag(timelapse_view.TAG)) == {lapse._items["entry"]}, str(sorted(lapse._items)))
check("no new toplevel",
      not [w for w in set(root.winfo_children()) - before - {window.win} if isinstance(w, tk.Toplevel)])
root.destroy()
