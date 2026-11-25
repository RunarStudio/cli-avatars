"""Child process for ``test_needs_you``: the Dungeon's Needs tab off-screen. Exit 77 when Tk has no display.

    python tests/_needs_you_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import needs_you  # noqa: E402
from cli_avatars.app import cues, needs_panel  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


data = Path(sys.argv[2])
reg = Registry(data)
set_topic(data, "forge", title="Forge", project="forge", status="open")
stuck = reg.task_create("forge", "Relight the forge", topic="forge")["id"]
reg.task_move(stuck, "doing")
reg.task_move(stuck, "blocked")
append_channel(data, {"ts": time.time() - 90, "from": "claude:room", "to": "user", "channel": "forge",
                      "icon": "speech", "note": "The bellows are torn.", "kind": "msg"})
played, chats, cards = [], [], []
cues.play = lambda _app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False, _chat_directory=lambda: data,
    _show_chat=lambda topic_id=None, address_id=None: chats.append(topic_id),
    _tasks_panel=SimpleNamespace(open_card=cards.append),
)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
view._ensure_tasks = noop
root.deiconify()
root.geometry("1100x600")
needs_panel.step(app, now=1.0)
root.update()
check("tab count", view._rtab_needs.button.cget("text") == "Needs you (2)", view._rtab_needs.button.cget("text"))
check("first read quiet", played == [], str(played))
view.set_right(True, "needs")
root.update()
panel = app._needs_panel
check("rows in order", panel.order == [f"card:{stuck}", "room:forge"], str(panel.order))
check("row text", panel.rows["room:forge"].title.cget("text") == "Forge"
      and panel.rows["room:forge"].tag.cget("text") == "REPLY")
kept = str(panel.rows["room:forge"].frame)
set_topic(data, "lantern", title="Lantern", project="lantern", status="open")
append_channel(data, {"ts": time.time() - 30, "from": "claude:room", "to": "user", "channel": "lantern",
                      "icon": "speech", "note": "Wick trimmed.", "kind": "msg"})
needs_panel.step(app, now=3.0)
root.update()
check("new item enters", panel.order[-1] == "room:lantern" and len(panel.rows) == 3, str(panel.order))
check("soft cue", played == ["arrive"], str(played))
check("in place", str(panel.rows["room:forge"].frame) == kept)
needs_panel.step(app, now=5.0)
check("no repeat cue", played == ["arrive"], str(played))
panel.rows["room:forge"].title.event_generate("<Button-1>")
panel.rows[f"card:{stuck}"].title.event_generate("<Button-1>")
root.update()
check("click opens", chats == ["forge"] and cards == [stuck] and view._center == "tasks", f"{chats} {cards}")
panel.rows["room:forge"].clear.invoke()
root.update()
check("clear", "room:forge" not in panel.rows and view._rtab_needs.button.cget("text") == "Needs you (2)")
check("clear stored", [r["key"] for r in needs_you.pending(data)] == [f"card:{stuck}", "room:lantern"])
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
