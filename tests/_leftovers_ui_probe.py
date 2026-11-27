"""Child process for ``test_leftovers_ui``: the centre tab strip, a scrolling Settings tab and the first tour callout
on an off-screen Dungeon window at 1366 x 768 with both side panels open. Made-up data; exit 77 without Tk.

    python tests/_leftovers_ui_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import scroll_tab, tour  # noqa: E402
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


host = _ProbeHost(root)
host.scanner = SimpleNamespace(bubbles=BubbleBoard())
host._chat_directory = lambda: data
host._show_chat = lambda topic_id=None, address_id=None: None
host._status_parent = None
host.dungeon = view = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
view.set_left(True)
view.set_right(True, "chat")
root.update()

# Memory tab: every centre tab sits inside the strip with both side panels open
mid = box(view._mid)
tabs = [view._tab_dungeon, view._tab_tasks, view._tab_throne, view._tab_recap, view._tab_mail, view._tab_repos,
        view._tab_projects, view._tab_memory]
check("both side panels open", view._left.winfo_ismapped() and view._right.winfo_ismapped())
out = [str(t.button.cget("text")) for t in tabs if not t.winfo_ismapped() or box(t)[2] > mid[2] or box(t)[0] < mid[0]]
check("every centre tab inside the strip", not out, f"{out} mid={mid} memory={box(view._tab_memory)}")
hidden = [str(t.button.cget("text")) for t in tabs
          if root.winfo_containing(t.button.winfo_rootx() + 4, t.button.winfo_rooty() + 4) is not t.button]
check("every centre tab on top, clickable", not hidden, hidden)
view.show_center("memory")
root.update()
check("Memory tab shown", view._center == "memory" and view._tab_memory.winfo_ismapped())

# Settings tab content taller than the dock scrolls with the wheel
holder = tk.Frame(root, width=360, height=300)
holder.place(x=0, y=0)
holder.pack_propagate(False)
nb = ttk.Notebook(holder)
nb.pack(fill="both", expand=True)
inner = scroll_tab.add(nb, " Long ", "#0d0d1a")
rows = [tk.Label(inner, text=f"row {i}") for i in range(40)]
for label in rows:
    label.pack(anchor="w")
root.update()
canvas = scroll_tab.canvas_of(inner)
check("tab content is taller than the tab", inner.winfo_reqheight() > canvas.winfo_height())
check("starts at the top", canvas.yview()[0] == 0.0, canvas.yview())
for _ in range(60):
    rows[3].event_generate("<MouseWheel>", delta=-120)
    rows[3].event_generate("<Button-5>")
root.update()
check("the wheel scrolls it", canvas.yview()[0] > 0.0 and canvas.yview()[1] == 1.0, canvas.yview())
rows.append(tk.Label(inner, text="added later"))
rows[-1].pack(anchor="w")
root.update()
rows[-1].event_generate("<MouseWheel>", delta=120)
root.update()
check("a row added later scrolls it too", canvas.yview()[1] < 1.0, canvas.yview())
holder.destroy()

# First tour callout stays off the centre view (the Throne Room's top-left)
view.show_center("throne")
root.update()
t = tour.start(host)
root.update()
card = box(t.card.outer)
mid = box(view._mid)
check("tour first step shown", t.alive() and t.shown == ["chat"])
check("callout off the centre view", card[2] <= mid[0], f"card={card} mid={mid}")
t.close()
root.destroy()
print("done")
