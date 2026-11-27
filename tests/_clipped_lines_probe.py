"""Child process for ``test_clipped_lines``: at 1366 x 768 with both side panels open, the Settings update lines
(the red reason, a check result and its subjects) and every Memory card line wrap and read in full. Made-up
data; exit 77 without Tk.

    python tests/_clipped_lines_probe.py <repo root> <data dir>

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

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import config_screen, update_ui  # noqa: E402
from cli_avatars.app import memory_notes as mn  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update.check import PHASE_NEWS, CheckResult  # noqa: E402

data = Path(sys.argv[2])
notes = data / "notes" / "memory"


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def box(widget) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def clipped(parent, outer) -> list[str]:
    """Text of every label under ``parent`` that is cut: wider than its box, or past ``outer``'s right edge."""
    out, stack = [], [parent]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if type(widget) is not tk.Label or not str(widget.cget("text")).strip():
            continue
        if widget.winfo_reqwidth() > widget.winfo_width() or box(widget)[2] > box(outer)[2]:
            out.append(str(widget.cget("text")))
    return out


mn.create(notes)
for cat, name, goal, status, nxt in (
        ("Garden", "compost", "black gold by spring for the raised beds", "active and turning every Sunday",
         "turn the heap and add the autumn leaves from the orchard path"),
        ("Kitchen", "sourdough", "an open crumb with a crackling crust", "active, rye starter on the counter",
         "feed the starter at 8 and again before bed")):
    folder = notes / "Topics" / cat
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(
        f"---\ntype: topic\nname: {name}\ntopic: {cat}/{name}\nstatus: {status}\nupdated: 2026-02-10\n---\n"
        f"Goal: {goal}\nStatus: {status}\nNext action: {nxt}\n", encoding="utf-8")

host = _ProbeHost(root)
host.config = {"memory": {"root": str(notes)}}
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

host._update_block = "PyInstaller is not installed (python -m PyInstaller --version failed)"
host._check = CheckResult(PHASE_NEWS, "3 new commits on dev since this build", 3,
                          ("Map scroll unrolls from the top of the parchment instead of the side",
                           "Quieter torches in the long hall"))
host._check_at = "09:14"
update_ui._fill(host)
root.update()
root.update()
panel = host._update_panel
texts = [str(w.cget("text")) for w in panel.winfo_children() if type(w) is tk.Label]
check("update lines shown", any("PyInstaller" in t for t in texts) and any("Quieter" in t for t in texts), texts)
cut = clipped(panel, view._settings)
check("every Settings update line reads in full", not cut, cut)

view.show_center("memory")
root.update()
host._memory_panel.refresh(force=True)
root.update()
root.update()
cards = host._memory_panel.cards
check("memory cards shown", len(cards.winfo_children()) == 2, cards.winfo_children())
cut = clipped(cards, view._memory)
check("every Memory card line reads in full", not cut, cut)
low = [c for c in cards.winfo_children() if c.winfo_height() < c.winfo_reqheight()]
check("cards grow to fit", not low, [(c.winfo_height(), c.winfo_reqheight()) for c in low])
root.destroy()
print("done")
