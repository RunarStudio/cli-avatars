"""Child process for ``test_tasks_tab``: the Tasks tab in an off-screen Dungeon. Exit 77 when Tk has no display.

    python tests/_tasks_tab_probe.py <repo root> <seeded data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402

AGENT = "claude:abcdef01"


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def texts(widget) -> list[str]:
    found = []
    for child in widget.winfo_children():
        try:
            found.append(str(child.cget("text")))
        except tk.TclError:
            pass
        found.extend(texts(child))
    return found


chat = SimpleNamespace(_topic_id="hooks")
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=chat, _chat_directory=lambda: sys.argv[2],
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.update()

strip = view._tab_dungeon.master.pack_slaves()
check("tab beside dungeon and skins", strip[:3] == [view._tab_dungeon, view._tab_skins, view._tab_tasks],
      str(strip))
view.show_center("tasks")
root.update()
panel = app._tasks_panel
check("tasks shown", view._center == "tasks" and view._tasks.winfo_manager() == "pack")
check("scene hidden", view.scene.winfo_manager() == "" and view._skins.winfo_manager() == "")
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
heads = [panel.headers[name].cget("text") for name in ("todo", "doing", "review", "done", "blocked")]
check("five column headers", heads == ["todo (2)", "doing (1)", "review (1)", "done (2) [+]", "blocked (1)"],
      str(heads))
check("done collapsed", panel.card_count("done") == 0 and panel.card_count("todo") == 2)
check("card meta", f"{AGENT} · 40% · 2/5" in texts(view._tasks), str(texts(view._tasks)))
panel.toggle_done()
root.update()
check("done expands", panel.card_count("done") == 2 and panel.headers["done"].cget("text") == "done (2) [-]")
before = panel.headers["todo"]
panel.refresh(force=True)
check("redraw skipped", panel.headers["todo"] is before)
chat._topic_id = ""
panel.refresh(force=True)
root.update()
check("empty state", panel.empty.winfo_manager() == "pack" and "No cards" in panel.empty.cget("text"))
panel.frame.focus_force()
root.update()
view.on_escape()
check("escape returns to dungeon", view._center == "dungeon" and view.scene.winfo_manager() == "pack")
root.destroy()
