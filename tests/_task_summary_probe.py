"""Child process for ``test_task_summary``: the card's "where we are" slip and the room pin. Exit 77 without Tk.

    python tests/_task_summary_probe.py <repo root> <empty work dir>

Prints ``ok <check>`` per check; any failed check exits 1. No CLI starts.
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

from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, room_log  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.room_pane import RoomPane, _Run  # noqa: E402
from cli_avatars.model.room import load_room  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

data = Path(sys.argv[2])


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


played = []
cues.play = lambda app, name: played.append(name)
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
reg = Registry(data)
made = reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
_card, chat = task_chats.start_chat(reg, made["id"], "claude")
room = chat["room"]

app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="west-keep"), _chat_directory=lambda: data,
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=noop,
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
card = panel.card_panel
panel.open_card(made["id"])
root.update()
check("no slip without a summary", not card.where.winfo_manager())

task_chats.apply_reply(data, room, ["TASK summary done: oiled both sconces | now: trimming wicks | next: light at dusk"],
                       "ok")
panel.refresh(force=True)
root.update()
slip = card.where
check("slip shows the three lines and the age", slip.winfo_manager() == "pack"
      and card.where_text.cget("text") == "done: oiled both sconces\nnow: trimming wicks\nnext: light at dusk"
      and card.where_age.cget("text") == "updated just now", (card.where_text.cget("text"), card.where_age.cget("text")))
task_chats.apply_reply(data, room, ["TASK summary done: wicks trimmed | now: waiting for dusk | next: light them"], "ok")
panel.refresh(force=True)
root.update()
check("slip updates in place", card.where is slip and card.where_text.cget("text").startswith("done: wicks trimmed"))
age = card.where_age
card.tick(now=card.where_ts + 7 * 60)
check("age ticks without a rebuild", card.where_age is age and age.cget("text") == "updated 7m ago", age.cget("text"))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
if len(sys.argv) > 3:
    from PIL import ImageGrab

    card.tick()
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(sys.argv[3])

window = ChatWindow(root, directory=data, agents=[], config={}, offscreen=True, room_pane=RoomPane)
window.open(topic_id=room)
for _ in range(2):
    window.refresh(force=True)
    root.update()
pane = window._room
check("room pin shows the task summary", pane._pin_box.winfo_manager() == "pack"
      and pane._pin_text.cget("text").startswith("done: wicks trimmed")
      and "Light the west torches" in pane._pin_title.cget("text"), pane._pin_text.cget("text"))
played.clear()
result = SimpleNamespace(outcome="ok", stderr="")
run = _Run(load_room(data, room), "claude", room_log.new_turn("claude"),
           texts=["Lit.\nTASK summary done: all lit | now: nothing | next: snuff at dawn"])
pane._on_done(run, result)
root.update()
check("turn end plays the cue once", played == ["arrive"] and pane._pin_text.cget("text").startswith("done: all lit"),
      (played, pane._pin_text.cget("text")))
run = _Run(load_room(data, room), "claude", room_log.new_turn("claude"),
           texts=["TASK summary done: lost | now: lost | next: lost"])
pane._on_done(run, SimpleNamespace(outcome="error", stderr=""))
root.update()
check("failed turn keeps the pin", played == ["arrive"] and pane._pin_text.cget("text").startswith("done: all lit"))
root.destroy()
print("done")
