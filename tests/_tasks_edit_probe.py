"""Child process for ``test_tasks_edit``: edit the board from the Tasks tab of a Dungeon. Exit 77 without a display.

    python tests/_tasks_edit_probe.py <repo root> <data dir with topic "hooks">

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


def at(widget) -> tuple[int, int]:
    return widget.winfo_rootx() + 10, widget.winfo_rooty() + 10


def mouse(widget, kind: str, point: tuple[int, int]) -> None:
    x, y = point
    held = {"state": 256} if kind == "<B1-Motion>" else {}
    widget.event_generate(kind, x=x - widget.winfo_rootx(), y=y - widget.winfo_rooty(), rootx=x, rooty=y, **held)
    root.update()


def press(name: str) -> None:
    next(b for row in card.sheet.winfo_children() for b in row.winfo_children()
         if isinstance(b, tk.Button) and b.cget("text") == name).invoke()
    root.update()


agents = {AGENT: SimpleNamespace(name="Rook", is_demo=False)}
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="hooks"), _chat_directory=lambda: sys.argv[2],
    scanner=SimpleNamespace(get_agents=lambda: agents),
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

check("empty topic shows columns", panel._main.winfo_manager() == "pack" and panel.empty.winfo_manager() == ""
      and panel.card_count("todo") == 0)
panel.new_button.invoke()
root.update()
check("new task opens the card panel", card.open and card.card is None)
card.create_button.invoke()
root.update()
check("field error shown", card.errors["title"].cget("text") == "A title is needed."
      and card.errors["title"].winfo_manager() == "pack")
card.title.insert(0, "Light the west torches")
card.create_button.invoke()
root.update()
check("card lands in todo", panel.card_count("todo") == 1 and not card.open
      and "Light the west torches" in texts(panel._bodies["todo"]))

[(card_id, box)] = panel.cards.items()
mouse(box, "<ButtonPress-1>", at(box))
mouse(box, "<ButtonRelease-1>", at(box))
check("card click opens panel", card.open and card.card["id"] == card_id)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])

for item in ("Fetch oil", "Trim wicks"):
    card.check_entry.insert(0, item)
    card._check_add()
root.update()
check("checklist added", [c.cget("text") for c in card.checks.winfo_children()] == ["Fetch oil", "Trim wicks"])
card.checks.winfo_children()[0].invoke()
root.update()
check("tick shows progress", "unassigned · 50% · 1/2" in texts(panel._bodies["todo"]), str(texts(panel._bodies["todo"])))

box = panel.cards[card_id]
doing = next(col for col, name in panel._columns.items() if name == "doing")
start, end = at(box), (doing.winfo_rootx() + doing.winfo_width() // 2, doing.winfo_rooty() + 120)
mouse(box, "<ButtonPress-1>", start)
mouse(box, "<B1-Motion>", (start[0] + 30, start[1]))
mouse(box, "<B1-Motion>", end)
lit = doing.cget("bg")
mouse(box, "<ButtonRelease-1>", end)
check("drag moves the card", panel.card_count("doing") == 1 and panel.card_count("todo") == 0
      and lit != panel._grid.cget("bg"), f"{panel.card_count('doing')} {lit}")

card._fill_menu()
labels = [card.assign_menu.entrycget(i, "label") for i in range(card.assign_menu.index("end") + 1)]
card.assign_menu.invoke(labels.index("Rook"))
root.update()
check("assign from menu", f"{AGENT} · 50% · 1/2" in texts(panel._bodies["doing"]) and card.card["assignee"] == AGENT
      and card.assign.cget("text") == "Rook ▾",
      str(labels))

card.column_buttons["done"].invoke()
root.update()
check("move button", panel.card_count("doing") == 0 and panel.headers["done"].cget("text") == "done (1) [+]"
      and card.column_buttons["done"].cget("bg") == "#ffcf4a")

card.comment_entry.insert(0, "Torches lit, hall is bright")
card._comment()
root.update()
check("comment in history", "daniel: Torches lit, hall is bright" in card.history.cget("text"))

panel.toggle_done()
root.update()
press("Archive")
check("archive hides card", panel.card_count("done") == 0 and not card.open)

panel.new_button.invoke()
root.update()
press("Cancel")
check("close panel", not card.open)
root.destroy()
