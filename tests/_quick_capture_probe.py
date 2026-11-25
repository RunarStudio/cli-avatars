"""Child process for ``test_quick_capture``: the capture strip in an off-screen Dungeon. Exit 77 without a display.

    python tests/_quick_capture_probe.py <repo root> <data dir seeded by test_quick_capture.seed>

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

from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.tasks_view import ALL  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA = Path(sys.argv[2])
errors: list[str] = []
root.report_callback_exception = lambda kind, value, tb: errors.append(f"{kind.__name__}: {value}")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def all_cards() -> list[dict]:
    reg = Registry(DATA)
    return [c for p in ("keep", "garden") for c in reg.task_list(p)]


def typed(text: str) -> None:
    strip.entry.delete(0, "end")
    strip.entry.insert(0, text)
    strip.entry.event_generate("<KeyRelease>", keysym="a")
    root.update()


played, shown = [], []
cues.play = lambda app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="west-wing"), _chat_directory=lambda: str(DATA),
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=lambda topic_id=None, address_id=None: shown.append(topic_id),
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
panel.set_filter(topic=ALL)
root.update()

panel.title.focus_force()
root.update()
panel.title.event_generate("<Control-space>")
root.update()
strip = view.capture
check("hotkey opens strip", strip.is_open() and strip.frame.winfo_manager() == "place"
      and root.focus_get() is strip.entry, f"{strip.is_open()} {root.focus_get()}")
check("fallback chip", strip.picked == "west-wing" and len(strip.chips) == 3, f"{strip.picked} {len(strip.chips)}")
typed("Buy new pruning shears for the apple rows")
check("ranker chips", strip.picked == "orchard" and strip.chips[0].topic == "orchard"
      and strip.chips[0].cget("text").startswith("Orchard")
      and all(c.winfo_ismapped() and c.winfo_width() > 20 for c in strip.chips),
      f"{strip.picked} {[(c.topic, c.winfo_width()) for c in strip.chips]}")

before = all_cards()
kept = {cid: box for cid, box in panel.cards.items()}
strip.entry.event_generate("<Return>")
root.update()
after = all_cards()
new = [c for c in after if c["id"] not in {b["id"] for b in before}]
check("enter saves one card", len(new) == 1 and new[0]["topic"] == "orchard" and new[0]["column"] == "todo"
      and not strip.is_open() and played[-1:] == ["capture"], f"{new} {strip.is_open()} {played}")
check("card lands in place", new[0]["id"] in panel.cards and all(panel.cards[c] is b for c, b in kept.items())
      and panel.cards[new[0]["id"]].master is panel._bodies["todo"], str(list(panel.cards)))

panel.title.event_generate("<Control-space>")
root.update()
typed("   ")
strip.entry.event_generate("<Return>")
root.update()
check("empty refused", strip.is_open() and strip.error.cget("text") and len(all_cards()) == len(after),
      strip.error.cget("text"))
strip.entry.event_generate("<Escape>")
root.update()
check("escape closes", not strip.is_open() and view._center == "tasks" and not strip.frame.winfo_manager())

panel.title.event_generate("<Control-space>")
root.update()
typed("Ask how the stairs railing should look")
strip.chat_btn.invoke()
strip.entry.event_generate("<Return>")
root.update()
fresh = [c for c in all_cards() if c["id"] not in {b["id"] for b in after}]
check("as chat", len(fresh) == 1 and fresh[0]["topic"] == "east-wing" and len(fresh[0]["chats"]) == 1
      and shown[-1:] == [fresh[0]["chats"][0]["room"]], f"{fresh} {shown}")

box = panel.cards[new[0]["id"]]
x, y = box.winfo_rootx() + 10, box.winfo_rooty() + 10
box.event_generate("<ButtonPress-1>", x=10, y=10, rootx=x, rooty=y)
box.event_generate("<ButtonRelease-1>", x=10, y=10, rootx=x, rooty=y)
root.update()
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
check("no callback errors", not errors, str(errors))
root.destroy()
