"""Child process for ``test_daily_recap_desktop``: the Dungeon's Recap tab off-screen. Exit 77 without a display.

    python tests/_daily_recap_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from board.store import LocalStore  # noqa: E402
from cli_avatars.app import cues, recap_panel  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

TODAY = date.today()


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def at(day: date, hour: int, minute: int = 0) -> str:
    local = datetime.combine(day, dtime(hour, minute)).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


data = Path(sys.argv[2])
reg = Registry(data)
set_topic(data, "forge", title="Forge", project="forge", status="open")
card = reg.task_create("forge", "Relight the forge", topic="forge")["id"]
room = f"task-{card[:8]}-1"
store = LocalStore(data)
store.update(card, lambda c: ({**c, "chats": [{"id": str(uuid.uuid4()), "cli": "claude",
                                               "created": at(TODAY, 8), "room": room}]}, []))


def add(kind, actor, ts, card_id=card, **fields):
    store.append_event({"id": str(uuid.uuid4()), "ts": ts, "card": card_id, "actor": actor, "kind": kind,
                        **fields}, project=None if card_id else "forge")


add("prompt", "daniel", at(TODAY, 0, 5), None, room=room, target="claude", outcome="ok")
add("summary", f"claude:{room}", at(TODAY, 0, 6), text="done: bellows\nnow: coal", via="chat")
add("moved", "daniel", at(TODAY - timedelta(days=1), 15), **{"from": "todo", "to": "doing"})

played, cards = [], []
cues.play = lambda _app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False, _chat_directory=lambda: data,
    _show_chat=noop, _tasks_panel=SimpleNamespace(open_card=cards.append),
)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
view._ensure_tasks = noop
root.deiconify()
root.geometry("1100x640")
root.update()
check("recap tab", view._tab_recap.button.cget("text") == "Recap")
view.show_center("recap")
root.update()
panel = app._recap_panel
check("shown", view._center == "recap" and view._recap.winfo_ismapped())
check("scroll cue", played == ["scroll"], str(played))
check("today", "Today" in panel.title_text(), panel.title_text())
keys = panel.order
check("grouped", keys[0] == "agent:claude:chats" and keys[1] == f"task:claude:chats:{card}"
      and "agent:daniel" in keys, str(keys))
lines = panel.texts()
check("lines", any("summary: done: bellows · now: coal" in t for t in lines)
      and any("chat 1 turn · ok" in t for t in lines) and any("commits: none logged" in t for t in lines))
ids = dict(panel.items)
add("summary", f"claude:{room}", at(TODAY, 0, 9), text="done: coal\nnow: spark", via="chat")
recap_panel.step(app, now=10.0)
root.update()
check("live", any("done: coal · now: spark" in t for t in panel.texts()), str(panel.texts()))
check("in place", all(panel.items.get(k) == v for k, v in ids.items() if k in panel.items)
      and set(ids) <= set(panel.items) and panel.rebuilds == 1, f"{panel.rebuilds}")
panel.canvas.focus_force()
root.update()
panel.canvas.event_generate("<Left>")
root.update()
check("previous day", "Yesterday" in panel.title_text() and any("moved todo → doing" in t for t in panel.texts())
      and not any("chat turn" in t for t in panel.texts()), panel.title_text())
panel.canvas.event_generate("<Right>")
panel.canvas.event_generate("<Right>")
root.update()
check("next stops at today", "Today" in panel.title_text(), panel.title_text())
for _ in range(40):
    panel.go(-1)
check("kept window", panel.day == TODAY - timedelta(days=29), str(panel.day))
panel.go(29)
panel.open_task(card)
root.update()
check("click opens card", cards == [card] and view._center == "tasks", str(cards))
view.show_center("recap")
root.update()
check("cue on open", played == ["scroll", "scroll"], str(played))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
