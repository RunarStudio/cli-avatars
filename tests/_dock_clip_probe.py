"""Child process for ``test_dock_clip``: at 1920 x 1080 (or the width given) with both side panels open, the chat
dock's Run and controls rows, the Grok topics strip and the open task card read in full. Made-up data; no CLI runs;
exit 77 without Tk.

    python tests/_dock_clip_probe.py <repo root> <data dir> <work dir> [width] [shot.png]

With ``shot.png`` it saves a shot of the chat and of the card.

Prints ``ok <check>`` or ``FAIL <check>`` per check, every check; any failed check exits 1 at the end.
"""

import os
import subprocess  # noqa: TID251  # patched to prove nothing here runs a process
import sys
import types
from pathlib import Path

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import bot_bridge  # noqa: E402
from bots.roster import parse_roster  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import chat, grok_topics  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.model.room import save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from grok_fake import install  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.task_chats import start_chat  # noqa: E402
from topics import set_topic  # noqa: E402

DATA, WORK = Path(sys.argv[2]), Path(sys.argv[3])
WIDTH = int(sys.argv[4]) if len(sys.argv) > 4 else 1920
SHOT = sys.argv[5] if len(sys.argv) > 5 else ""
_SLACK = 4  # px a widget may ask beyond its box without losing a glyph
_TEXT = (tk.Label, tk.Button, tk.Checkbutton, tk.Menubutton)


failed: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        failed.append(name)
        return
    print(f"ok {name}")


def box(widget) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def clipped(parent, outer, skip=()) -> list[str]:
    """Text of every label, button or menu under ``parent`` that is cut: packed but squeezed out of sight, narrower
    than it asks, or past ``outer``'s right edge."""
    out, stack = [], [parent]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if widget in skip or not isinstance(widget, _TEXT) or not str(widget.cget("text")).strip():
            continue
        if not widget.winfo_ismapped():
            if widget.winfo_manager() and widget.master.winfo_ismapped():
                out.append(str(widget.cget("text")))
            continue
        if widget.winfo_reqwidth() > widget.winfo_width() + _SLACK or box(widget)[2] > box(outer)[2]:
            out.append(str(widget.cget("text")))
    return out


def snap(name: str) -> None:
    if SHOT:
        from PIL import ImageGrab

        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab((x, y, x + WIDTH, y + 1080)).save(SHOT.replace(".png", f"-{name}.png"))


ran: list = []
subprocess.Popen = lambda *a, **k: ran.append(a)  # type: ignore[assignment]
WORK.mkdir(parents=True, exist_ok=True)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(install(WORK)),
                                                          templated=True))
save_binary_pin(DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
set_topic(DATA, "lantern", title="Lantern workshop in the east wing", project="lantern", status="open")
for _ in range(2):
    grok_topics.new_topic(DATA, "lantern")
registry = Registry(DATA)
card = registry.task_create("lantern", "Polish the brass lantern for the night market", topic="lantern")["id"]
for cli in ("grok", "claude"):
    start_chat(registry, card, cli)
asked = registry.task_create("lantern", "Hang the lantern over the north gate", topic="lantern")["id"]
roster = parse_roster({"schema_version": 1, "groups": [{"id": "forge", "name": "Forge", "collapsed": False, "order": 0}],
                       "bots": [{"id": "brass-scout", "name": "Brass Scout", "emoji": "", "group_id": "forge",
                                 "skin": "caine"}]})
bot_bridge.ask(DATA, bot_bridge.root(DATA, {}), roster, "brass-scout",
               "Which hook on the north gate holds a brass lantern through a windy night?", card=asked)

host = _ProbeHost(root)
host.scanner = types.SimpleNamespace(bubbles=BubbleBoard(), get_agents=lambda: {})
host._chat_directory = lambda: DATA
host._rooms_records = lambda: []
host._status_parent = None
for name in ("_ensure_chat_window", "_show_chat", "_paint_chat_button", "_remember_chat_box"):
    setattr(host, name, types.MethodType(getattr(chat, name), host))
host._chat_btn = None
host.dungeon = view = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()
root.geometry(f"{WIDTH}x1080+0+0")
root.update()
view.set_left(True)
host._show_chat(topic_id="lantern")
for _ in range(4):
    root.update()
pane = host._chat_window._room
pane.pick_target("grok")
for _ in range(3):
    root.update()
check("chat docked on the room", host._chat_window._topic_id == "lantern" and view._right.winfo_ismapped()
      and view._left.winfo_ismapped())
check("Grok strip shown", pane.grok.frame.winfo_ismapped() and len(pane.grok.rows) >= 2, pane.grok.rows)
snap("chat")
run_row = pane.chips["grok"].master
cut = clipped(run_row, view._right) + clipped(pane._ask_btn.master, view._right)
check("Run and controls rows read in full", not cut, cut)
cut = clipped(pane.grok.frame, view._right)
check("Grok topics strip reads in full", not cut, cut)
cut = clipped(pane._composer, view._right, skip=(host._chat_window._status,))  # the status line: chat_window.py
check("every composer line reads in full", not cut, cut)
status = host._chat_window._status
cut = clipped(status.master, view._right)
check("status hint reads in full", str(status.cget("text")).startswith("Enter runs Grok") and not cut,
      (status.cget("text"), cut))

view.show_center("tasks")
root.update()
panel = host._tasks_panel
panel.open_card(card)
for _ in range(3):
    root.update()
sheet = panel.card_panel.sheet
check("task card open", sheet.winfo_ismapped())
snap("card")
cut = clipped(sheet, panel.card_panel.frame)
check("task card reads in full", not cut, cut)
panel.open_card(asked)
for _ in range(3):
    root.update()
asks = [str(w.cget("text")) for line in panel.card_panel.asks.rows.winfo_children() for w in line.winfo_children()]
check("bot ask row shown", any(t.startswith("Brass Scout:") for t in asks), asks)
cut = clipped(panel.card_panel.sheet, panel.card_panel.frame)
check("task card with a bot ask reads in full", not cut, cut)
check("no CLI ran", not ran, ran)
root.destroy()
print("done")
raise SystemExit(1 if failed else 0)
