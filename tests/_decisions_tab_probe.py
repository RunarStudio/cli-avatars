"""Child process for ``test_task_decisions``: decisions on the Tasks tab, off-screen. Exit 77 without a display.

    python tests/_decisions_tab_probe.py <repo root> <seeded data dir> <mine card id> <decision id>

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
from decisions import list_decisions  # noqa: E402

DIR, MINE, ASKED = sys.argv[2], sys.argv[3], sys.argv[4]


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


opened = []
chat = SimpleNamespace(_topic_id="lantern")
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=chat, _chat_directory=lambda: DIR,
    _show_chat=lambda topic_id=None, address_id=None: opened.append(topic_id),
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
check("decisions button counts", panel.decisions_button.cget("text") == "Decisions (2)",
      panel.decisions_button.cget("text"))
check("card tag", "DECIDE" in texts(panel.cards[MINE]), str(texts(panel.cards[MINE])))
heads = [panel.headers[name].cget("text") for name in ("todo", "doing")]
check("column mark", heads[0] == "todo (3) ◆2" and heads[1] == "doing (0)", str(heads))
chat._topic_id = "gate"
panel.toggle_decisions()
root.update()
check("filter shows every topic", panel.title.cget("text") == "Decisions · every topic" and len(panel.cards) == 2,
      f"{panel.title.cget('text')} {len(panel.cards)}")
panel.open_card(MINE)
root.update()
card_texts = texts(panel.card_panel.sheet)
check("slip shows the question", "Clear or smoked glass?" in card_texts and "claude:1a2b3c4d asks" in card_texts,
      str(card_texts[:12]))
check("options as buttons", "b  Smoked" in card_texts)
panel.card_panel.decide_entries[ASKED].insert(0, "thin")
picks = [w for w in panel.card_panel.decide_box.winfo_children()[0].winfo_children()
         if isinstance(w, tk.Button) and w.cget("text") == "b  Smoked"]
picks[0].invoke()
root.update()
row = next(r for r in list_decisions(DIR) if r["id"] == ASKED)
check("answered from the card", row["status"] == "answered" and row["choice"] == "b" and row["answer"] == "thin",
      str(row))
check("slip gone", not panel.card_panel.decide_box.winfo_children())
check("no gap left", panel.card_panel.decide_box.winfo_height() <= 2,
      str(panel.card_panel.decide_box.winfo_height()))
check("count drops", panel.decisions_button.cget("text") == "Decisions (1)", panel.decisions_button.cget("text"))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
