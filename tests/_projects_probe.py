"""Child process for ``test_projects_desktop``: the Projects tab in the Dungeon window, off-screen, on made-up data.
Exit 77 without a display.

    python tests/_projects_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1. Start chat opens a stand-in chat pane; no CLI runs.
"""

import os
import subprocess  # noqa: TID251  # patched to prove Start chat runs nothing
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import projects_view as pv  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars_mcp.projects import save_project  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, set_topic  # noqa: E402

DATA = Path(sys.argv[2])


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out.extend(texts(child))
    return out


ran: list = []
subprocess.Popen = lambda *a, **k: ran.append(a)  # type: ignore[assignment]
save_project(DATA, {"slug": "lantern", "name": "Lantern", "path": "/srv/made-up/lantern-works", "status": "active",
                    "topics": ["glass-orchard"]})
save_project(DATA, {"slug": "quiet-moth", "name": "Quiet Moth", "status": "idea"})
ensure_topic(DATA, "glass-orchard", title="Glass orchard")
ensure_topic(DATA, "moth", title="Moth")
set_topic(DATA, "moth", project="quiet-moth")
reg = Registry(DATA)
card = reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
reg.task_move(card["id"], "doing")
reg.task_create("quiet-moth", "Moth wings", topic="moth")

opened, picked = [], []
entry = tk.Entry(root)
pane = SimpleNamespace(refresh_clis=noop, pick_target=picked.append)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False, _chat_directory=lambda: DATA,
    scanner=SimpleNamespace(get_agents=dict), _chat_window=SimpleNamespace(_room=pane, _entry=entry),
)
app._show_chat = lambda topic_id=None, address_id=None: opened.append(topic_id)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
root.deiconify()
root.geometry("1366x768")
root.update()
tops_before = len(root.winfo_children())

view.show_center("projects")
root.update()
panel = getattr(app, "_projects_panel", None)
check("projects tab", view._center == "projects" and panel is not None and view._projects.winfo_ismapped())
check("one row per project", set(panel.rows) == {"lantern", "quiet-moth"}, str(panel.rows))
shown = " ".join(texts(view._projects))
check("row shows counts and folder", "1 doing" in shown and "lantern-works" in shown, shown)
check("no full path shown", "/srv" not in shown)

panel.toggle("lantern")
root.update()
shown = " ".join(texts(view._projects))
check("expanded shows tasks topics chats repos decisions",
      all(w in shown for w in ("Count the glass apples", "Glass orchard", "Tasks", "Topics", "Chats", "Repos",
                               "Decisions")), shown)

panel.pick_column("todo")
root.update()
check("filter by column", set(panel.rows) == {"quiet-moth"}, str(panel.rows))
panel.pick_column("")
root.update()

panel.start("task", card["id"])
root.update()
check("task start chat opens its task chat", opened and opened[-1].startswith("task-"), str(opened))
check("cli picked", picked and picked[-1] == panel.cli.get(), str(picked))
check("task chat has no draft", entry.get() == "")
panel.start("topic", "glass-orchard")
root.update()
check("topic start chat opens the topic with the context as a draft", opened[-1] == "glass-orchard"
      and pv.HEAD in entry.get(), entry.get()[:80])
entry.delete(0, "end")
panel.start("project", "quiet-moth")
root.update()
check("project start chat opens its topic", opened[-1] == "moth" and "Quiet Moth" in entry.get(), str(opened))
check("no cli started", not ran, str(ran))
check("reads throttled", panel._read.interval >= 0.5)
check("no new toplevel", len(root.winfo_children()) == tops_before)
root.destroy()
