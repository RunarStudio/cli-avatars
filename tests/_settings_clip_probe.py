"""Child process for ``test_settings_clip``: at 1920 x 1080 with the right panel on Settings, every line and button of
Chat (Chat tiers) and Bots (hidden · last seen, each bot's menus) reads in full, and so does every other tab. Made-up data; exit 77 without Tk.

    python tests/_settings_clip_probe.py <repo root> <data dir> [shot.png]

With ``shot.png`` it saves a shot per tab and goes on past a failed check.

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import sys
import time
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

from bots.service import BotService  # noqa: E402
from bots.status import BotStatus  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import config_screen  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402

data = Path(sys.argv[2])
shot = sys.argv[3] if len(sys.argv) > 3 else ""
_SLACK = 4  # px a wrapped line may ask beyond its box without losing a glyph
_TEXT = (tk.Label, tk.Button, tk.Checkbutton, tk.Menubutton)


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        if not shot:
            raise SystemExit(1)
        return
    print(f"ok {name}")


def box(widget) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def clipped(parent, outer) -> list[str]:
    """Text of every label, button or menu under ``parent`` that is cut: packed but squeezed out of sight, narrower
    than it asks, or past ``outer``'s right edge."""
    out, stack = [], [parent]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not isinstance(widget, _TEXT) or not str(widget.cget("text")).strip():
            continue
        if not widget.winfo_ismapped():
            if widget.winfo_manager() and widget.master.winfo_ismapped():
                out.append(str(widget.cget("text")))
            continue
        if widget.winfo_reqwidth() > widget.winfo_width() + _SLACK or box(widget)[2] > box(outer)[2]:
            out.append(str(widget.cget("text")))
    return out


bots = BotService(data)
bots.import_example()
now = time.time()
roster = [bot for _group, rows in bots.sections() for bot, _status in rows]
bots._statuses = {bot.id: BotStatus(bot.id, "idle", "", "", now - 5 * 3600) for bot in roster}
bots._polled = now

host = _ProbeHost(root)
host.bots = bots
host.scanner = SimpleNamespace(bubbles=BubbleBoard(), get_agents=lambda: {})
host._chat_directory = lambda: data
host._show_chat = lambda topic_id=None, address_id=None: None
host._status_parent = None
host._build_config_ui = lambda win: config_screen._build_config_ui(host, win)
host.dungeon = view = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()
root.geometry("1920x1080+0+0")
root.update()
view.set_right(True, "settings")
root.update()
check("right panel on Settings", view._right.winfo_ismapped() and view._settings.winfo_ismapped())
nb = next(w for w in view._settings.winfo_children() if isinstance(w, ttk.Notebook))
tabs = {str(nb.tab(t, "text")).strip(): t for t in nb.tabs()}


def show(name: str, at: float = 0.0, snap: bool = False) -> tk.Widget:
    nb.select(tabs[name])
    for _ in range(3):
        root.update()
    page = root.nametowidget(tabs[name])
    canvas = next(w for w in page.winfo_children() if isinstance(w, tk.Canvas))
    canvas.yview_moveto(at)
    root.update()
    if shot and snap:
        from PIL import ImageGrab

        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab((x, y, x + 1920, y + 1080)).save(shot.replace(".png", f"-{name.lower()}.png"))
    return page


page = show("Chat", snap=True)
rows = host._tier_settings
check("tier rows shown", all(r["reset"].winfo_ismapped() for r in rows.values()), rows)
cut = clipped(page, view._settings)
check("every Chat tab line reads in full", not cut, cut)
page = show("Bots", 0.4, snap=True)
check("bots hidden", all(bots.hidden(bot.id) for bot in roster) and roster, roster)
cut = clipped(page, view._settings)
check("every Bots tab line reads in full", not cut, cut)
cut = {}
for name in tabs:
    for at in (0.0, 0.5, 1.0):
        cut.update({f"{name}: {text}": at for text in clipped(show(name, at), view._settings)})
check("every Settings tab line reads in full", not cut, sorted(cut))
root.destroy()
print("done")
