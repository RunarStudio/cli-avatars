"""Child process for ``test_focus_desktop``: the board's Focus and the floor veil in an off-screen Dungeon.
Exit 77 without a display.

    python tests/_focus_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
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

import focus  # noqa: E402
from cli_avatars.app import cues, focus_mode, focus_veil  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

DATA = Path(sys.argv[2])


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def shown_cards() -> list[str]:
    return sorted(panel.cards)


set_topic(DATA, "moon-forge", title="Moon forge", project="lantern", status="open")
reg = Registry(DATA)
gate = reg.task_create("lantern", "Polish the moon gate", topic="moon-forge")["id"]
keys = reg.task_create("lantern", "Forge three silver keys", topic="moon-forge")["id"]
reg.task_move(gate, "doing")
played = []
cues.play = lambda _app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="moon-forge"), _chat_directory=lambda: DATA,
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=noop,
)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
panel.refresh(force=True)
root.update()
before = set(root.winfo_children())

menu = panel.move_menu(gate)
labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
check("menu entry", any(label.startswith("Focus on this task") for label in labels), str(labels))
box = panel.cards[gate]
box.focus_force()
box.event_generate("<KeyPress-f>")
root.update()
check("f key focuses", focus.current(DATA) == gate, str(focus.current(DATA)))
check("board shows one card", shown_cards() == [gate], str(shown_cards()))
check("focus title", panel.title.cget("text") == "Focus · Polish the moon gate", panel.title.cget("text"))
check("leave button", bool(panel.leave_button.winfo_manager()))
menu = panel.move_menu(gate)
labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
check("menu leave entry", "Leave focus" in labels, str(labels))
panel.cards[gate].event_generate("<KeyPress-F>")
root.update()
check("f again leaves", focus.current(DATA) is None)
check("board back", shown_cards() == sorted([gate, keys]) and not panel.leave_button.winfo_manager(),
      str(shown_cards()))

model = sr.SessionRooms(DATA / "ui" / "session_rooms.json")
model.open(sr.SIMPLE, "claude", "moon-forge")
model.open(sr.SIMPLE, "claude", "glass-orchard")
canvas = tk.Canvas(root, width=900, height=600)
canvas.place(x=0, y=0)
canvas._rooms_painter = RoomsPainter(source=lambda: model.layout(0.0))
root.update()
canvas._rooms_painter.paint(canvas)
book = SimpleNamespace(app=app)
focus_mode.start(app, gate)
for t in (10.0, 10.2, 10.4, 10.6):
    focus_veil.paint(book, canvas, None, t)
veil = focus_veil.veil_for(book)
items = dict(veil._items)
check("veil drawn", {"veil", "light"} <= set(items) and bool(canvas.find_withtag(focus_veil.TAG)), str(items))
check("banner", "banner" in items and bool(canvas.find_withtag(focus_veil.LEAVE)))
focus_veil.paint(book, canvas, None, 11.0)
check("in place", veil._items == items, f"{items} {veil._items}")
veil._leave(canvas)
check("leave click", focus.current(DATA) is None and played[-1] == "unfocus", str(played))
for t in (12.0, 12.2, 12.4, 12.6):
    focus_veil.paint(book, canvas, None, t)
check("veil gone", not canvas.find_withtag(focus_veil.TAG) and not canvas.find_withtag(focus_veil.BANNER))
check("no new toplevel", not [w for w in set(root.winfo_children()) - before if isinstance(w, tk.Toplevel)])
root.destroy()
