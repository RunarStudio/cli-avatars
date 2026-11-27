"""Child process for ``test_dock_tabs``: the right panel at 1366 x 768 with both side panels open; its Pop out
button and tabs sit inside it, and every Settings tab name reads in full. Made-up data; exit 77 without Tk.

    python tests/_dock_tabs_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import config_screen  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402

data = Path(sys.argv[2])


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def box(widget) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def inside(widget, outer) -> bool:
    a, b = box(widget), box(outer)
    return widget.winfo_ismapped() and a[0] >= b[0] and a[2] <= b[2] and widget.winfo_width() >= widget.winfo_reqwidth()


host = _ProbeHost(root)
host.scanner = SimpleNamespace(bubbles=BubbleBoard(), get_agents=lambda: {})
host._chat_directory = lambda: data
host._show_chat = lambda topic_id=None, address_id=None: None
host._status_parent = None
host._build_config_ui = lambda win: config_screen._build_config_ui(host, win)
host.dungeon = view = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.set_left(True)
view.set_right(True, "settings")
root.update()
check("both side panels open", view._left.winfo_ismapped() and view._right.winfo_ismapped())
check("Pop out inside the right panel", inside(view._pop_btn, view._right),
      f"pop={box(view._pop_btn)} req={view._pop_btn.winfo_reqwidth()} right={box(view._right)}")
tabs = [view._rtab_chat, view._rtab_needs, view._rtab_settings]
out = [str(t.button.cget("text")) for t in tabs if not t.winfo_ismapped() or box(t)[2] > box(view._pop_btn)[0]]
check("every right tab left of Pop out", not out, out)

nb = next((w for w in view._settings.winfo_children() if isinstance(w, ttk.Notebook)), None)
check("Settings built", nb is not None and len(nb.tabs()) >= 7, view._settings.winfo_children())
names = [str(nb.tab(t, "text")).strip() for t in nb.tabs()]
shown = {}
stack = [view._settings]
while stack:
    widget = stack.pop()
    stack.extend(widget.winfo_children())
    try:
        text = str(widget.cget("text")).strip()
    except tk.TclError:
        continue
    if text in names and inside(widget, view._settings):
        shown[text] = widget
check("every Settings tab name reads in full", set(shown) == set(names), sorted(set(names) - set(shown)))
shown["Chat"].invoke()
root.update()
check("a tab name opens its tab", str(nb.tab(nb.select(), "text")).strip() == "Chat", nb.tab(nb.select(), "text"))
nb.select(nb.tabs()[0])
root.update()
check("the selected tab is marked", str(shown[names[0]].cget("bg")) != str(shown["Chat"].cget("bg")))
root.destroy()
print("done")
