"""Child process for ``test_tasks_learnt``: drop a card in Done and answer "What did we learn?". Exit 77 without a display.

    python tests/_tasks_learnt_probe.py <repo root> <data dir with topic "hooks">

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
from registry.facade import Registry  # noqa: E402


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


def at(widget) -> tuple[int, int]:
    return widget.winfo_rootx() + 10, widget.winfo_rooty() + 10


def mouse(widget, kind: str, point: tuple[int, int]) -> None:
    x, y = point
    held = {"state": 256} if kind == "<B1-Motion>" else {}
    widget.event_generate(kind, x=x - widget.winfo_rootx(), y=y - widget.winfo_rooty(), rootx=x, rooty=y, **held)
    root.update()


def drag(box, column: str) -> None:
    target = next(col for col, name in panel._columns.items() if name == column)
    start, end = at(box), (target.winfo_rootx() + target.winfo_width() // 2, target.winfo_rooty() + 60)
    mouse(box, "<ButtonPress-1>", start)
    mouse(box, "<B1-Motion>", (start[0] + 30, start[1]))
    mouse(box, "<B1-Motion>", end)
    mouse(box, "<ButtonRelease-1>", end)


registry = Registry(sys.argv[2])
first = registry.task_create("demo-app", "Light the west torches", topic="hooks")["id"]
second = registry.task_create("demo-app", "Trim the wicks", topic="hooks")["id"]
for cid in (first, second):
    registry.task_move(cid, "doing")

app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="hooks"), _chat_directory=lambda: sys.argv[2],
    scanner=SimpleNamespace(get_agents=lambda: {}),
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1200x720+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
card = panel.card_panel

check("badge on card", "DOING" in texts(panel.cards[first]), str(texts(panel.cards[first])))

drag(panel.cards[second], "done")
check("drop in done asks", card.open and card.card["id"] == second and card.learnt_frame.winfo_manager() == "pack"
      and card.learnt_prompt.cget("text") == "What did we learn?")
card.skip_button.invoke()
root.update()
check("skip closes", not card.open and registry.task_get(second)["learnt"] == "")

drag(panel.cards[first], "done")
card.learnt_entry.insert(0, "Oil the sconces before the wicks")
card.learnt_save.invoke()
root.update()
check("save learnt", registry.task_get(first)["learnt"] == "Oil the sconces before the wicks"
      and card.errors["learnt"].cget("text") == "")
panel.toggle_done()
root.update()
check("learnt shown", any("Oil the sconces" in t for t in texts(panel.cards[first]))
      and "DONE" in texts(panel.cards[first]), str(texts(panel.cards[first])))
root.destroy()
