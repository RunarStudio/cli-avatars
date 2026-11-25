"""Child process for ``test_task_chats``: the card panel's Chats section in a Dungeon. Exit 77 without a display.

    python tests/_task_chat_probe.py <repo root> <data dir with topic "west-keep" and one card>

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

from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


played, shown = [], []
cues.play = lambda app, name: played.append(name)
chat = SimpleNamespace(_topic_id="west-keep")


def show_chat(topic_id=None, address_id=None):
    shown.append(topic_id)
    chat._topic_id = topic_id


app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=chat, _chat_directory=lambda: sys.argv[2],
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=show_chat,
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
[card_id] = panel.cards
panel.open_card(card_id)
root.update()
check("card shows an empty chats list", card.open and not [w for w in card.chat_list.winfo_children()
                                                          if isinstance(w, tk.Frame)])
check("grok waits with its reason", str(card.chat_buttons["grok"].cget("state")) == "disabled"
      and "grok login" in card.chat_buttons["grok"].why)
check("no cli started yet", not shown and not played)
card.chat_buttons["claude"].invoke()
root.update()
rooms = [c["room"] for c in card.card["chats"]]
check("new chat opens its room with the cue", len(rooms) == 1 and shown == rooms and played == ["arrive"],
      f"{rooms} {shown} {played}")
check("board stays on the card's topic", panel._topic() == "west-keep" and card_id in panel.cards)
card.chat_buttons["claude"].invoke()
root.update()
tiles = [w for w in card.chat_list.winfo_children() if isinstance(w, tk.Frame)]
check("two chats listed", len(tiles) == 2 and [t.room for t in tiles] == [c["room"] for c in card.card["chats"]])
tiles[0].event_generate("<Button-1>")
root.update()
check("click reopens a chat", shown[-1] == tiles[0].room and played == ["arrive", "arrive"])
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
from registry.facade import Registry  # noqa: E402
from registry.task_chats import apply  # noqa: E402

apply(Registry(sys.argv[2]), tiles[0].room, card_id, "check", 1)
panel.refresh(force=True)
root.update()
check("the chat's tick shows in the open card", card.card["checklist"][0]["done"]
      and card.checks.winfo_children()[0].cget("text") == "Trim the wicks")
if len(sys.argv) > 3:
    root.update()
    from PIL import ImageGrab

    x, y = card.frame.winfo_rootx(), card.frame.winfo_rooty()
    ImageGrab.grab((x, y, x + card.frame.winfo_width(), y + card.frame.winfo_height())).save(sys.argv[3])
print("done")
