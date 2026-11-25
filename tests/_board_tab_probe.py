"""Child process for ``test_board_tab``: the Tasks board in an off-screen Dungeon. Exit 77 without a display.

    python tests/_board_tab_probe.py <repo root> <data dir seeded by test_board_tab.seed>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.main import _selftest_tasks  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA = Path(sys.argv[2])


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


def titles(name: str) -> list[str]:
    return sorted(t for t in texts(panel._bodies[name]) if t.startswith("Card "))


def by_title(title: str) -> str:
    return next(cid for cid, (card, _box) in panel._tiles.items() if card.title == title)


def moved() -> list[dict]:
    return [json.loads(line) for p in sorted((DATA / "board").glob("*/events.jsonl"))
            for line in p.read_text().splitlines() if '"moved"' in line]


played, shown = [], []
cues.play = lambda app, name: played.append(name)
chat = SimpleNamespace(_topic_id="west-wing")


def show_chat(topic_id=None, address_id=None):
    shown.append(topic_id)


app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=chat, _chat_directory=lambda: str(DATA),
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=show_chat,
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel

check("filter bar", panel.project_button.cget("text") == "All projects ▾"
      and panel.topic_button.cget("text") == "Chat topic ▾" and titles("todo") == ["Card torch", "Card vines"],
      f"{panel.project_button.cget('text')} {panel.topic_button.cget('text')} {titles('todo')}")
panel._fill_projects()
labels = [panel.project_button.menu.entrycget(i, "label") for i in range(panel.project_button.menu.index("end") + 1)]
panel.project_button.menu.invoke(labels.index("keep"))
root.update()
check("project filter", titles("todo") == ["Card torch"] and panel.title.cget("text") == "Board · keep · west-wing",
      f"{labels} {titles('todo')} {panel.title.cget('text')}")
panel._fill_topics()
menu = panel.topic_button.menu
labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
menu.invoke(labels.index("All topics"))
root.update()
check("topic filter all", titles("review") == ["Card stairs"] and titles("blocked") == []
      and labels[:2] == ["Chat topic (west-wing)", "All topics"], f"{labels} {titles('review')}")

gate = by_title("Card gate")
line = panel.chat_lines.get(gate)
said = texts(panel.cards[gate])
check("chat line", line is not None and any(t.startswith("2 chats · Rune four is cut") for t in said)
      and not any("ghp_" in t for t in said), str(said))
line.winfo_children()[-1].event_generate("<ButtonRelease-1>")
root.update()
rooms = [c["room"] for c in Registry(DATA).task_get(gate)["chats"]]
check("chat click opens chat", shown == [rooms[1]] and not panel.card_panel.open, f"{shown} {rooms}")

torch = by_title("Card torch")
box = panel.cards[torch]
doing = next(col for col, name in panel._columns.items() if name == "doing")
start, end = at(box), (doing.winfo_rootx() + doing.winfo_width() // 2, doing.winfo_rooty() + 200)
before = len(moved())
mouse(box, "<ButtonPress-1>", start)
mouse(box, "<B1-Motion>", (start[0] + 30, start[1]))
mouse(box, "<B1-Motion>", end)
mouse(box, "<ButtonRelease-1>", end)
check("drag moves with cue", titles("doing") == ["Card gate", "Card torch"] and played == ["move"],
      f"{titles('doing')} {played}")
new = moved()[before:]
check("one moved event", [(e["actor"], e["from"], e["to"]) for e in new] == [("daniel", "todo", "doing")], str(new))

reg = Registry(DATA)
stairs = by_title("Card stairs")
keep = {cid: box for cid, box in panel.cards.items() if cid != stairs}
times = []
for value in (20, 40, 60):
    reg.task_progress(stairs, value, "agent update")
    panel.refresh(force=True)
    root.update()
    times.append(panel.draw_ms)
check("in place update", all(panel.cards[cid] is box for cid, box in keep.items())
      and "agent update" in texts(panel.cards[stairs]), str(texts(panel.cards[stairs])))
check("draw under 2 ms", min(times) <= 2.0, str(times))
print(f"draw ms {min(times):.3f} (runs {', '.join(f'{t:.3f}' for t in times)})")

menu = panel.move_menu(stairs)
labels = [menu.entrycget(i, "label") if menu.type(i) != "separator" else "" for i in range(menu.index("end") + 1)]
menu.invoke(labels.index("  BLOCKED"))
root.update()
check("menu move", titles("blocked") == ["Card stairs"] and "  REVIEW" not in labels and "  TODO" in labels
      and played == ["move", "move"], f"{labels} {titles('blocked')}")

panel.cards[torch].focus_force()
root.update()
panel.cards[torch].event_generate("<Control-Right>")
root.update()
check("keyboard move", titles("review") == ["Card torch"] and len(moved()) == before + 3,
      f"{titles('review')} {len(moved())}")
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
problems = _selftest_tasks(root)
check("selftest tasks", problems == [], str(problems))
root.destroy()
