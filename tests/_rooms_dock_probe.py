"""Child process for ``test_rooms_dock``: the Topics dock off-screen. Exit 77 when Tk has no display.

    python tests/_rooms_dock_probe.py <repo root> <temp dir>

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
from cli_avatars.app import rooms_panel  # noqa: E402
from cli_avatars.app.dungeon_panes import repack  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402

NOW = 1_795_000_000.0
clock = SimpleNamespace(now=NOW)
rooms_panel.time = SimpleNamespace(time=lambda: clock.now)
DATA = Path(sys.argv[2])
agents = {
    f"orch-{i:02d}": SimpleNamespace(
        agent_id=f"orch-{i:02d}", name=f"Orch-{i:02d}", status="idle", source="claude", project="",
        parent_id=None, last_seen=NOW - 600 - i, skin="caine", is_demo=False, failed=False, subagents=0,
    )
    for i in range(40)
}

host = OverlayApp.__new__(OverlayApp)
host.root = root
host.config = {}
host._config_path = DATA / "config.json"
for key, value in dict(_rooms_shown=True, _chat_shown=False, _rooms_btn=None, _chat_btn=None, _rooms_sig=None,
                       _rooms_thumbs={}, _rooms_warns={}, _bot_photos=[], _bot_vars=[], _topics_stamp=None,
                       sub_avatars={}, desktop_escape=False, bots=None).items():
    setattr(host, key, value)
host.scanner = SimpleNamespace(get_agents=lambda: agents, bubbles=BubbleBoard(),
                               _events=SimpleNamespace(data_dir=DATA))
host.dungeon = DungeonWindow(host)
host.dungeon.build(offscreen=True)
host.dungeon._right_open = False
repack(host.dungeon)
root.geometry("640x480+20000+20000")
root.deiconify()
host._build_rooms_win()
host._update_rooms_win(True)
root.update()
canvas = host._rooms_canvas
panel = rooms_panel.RoomsPanel(host)


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def widgets() -> set:
    found, todo = set(), [host._rooms_list]
    while todo:
        for child in todo.pop().winfo_children():
            found.add(str(child))
            todo.append(child)
    return found


def texts() -> list:
    out = []
    for name in sorted(widgets()):
        widget = root.nametowidget(name)
        if isinstance(widget, tk.Label):
            out.append(widget.cget("text"))
    return out


def tick(seconds: float) -> None:
    clock.now += seconds
    panel.refresh()
    root.update()


before = widgets()
for _ in range(4):
    tick(1.0)
check("ticks keep every widget", widgets() == before, f"{len(before - widgets())} replaced")
check("age text moves", "604s ago" in texts(), str([t for t in texts() if t.endswith("ago")][:3]))

row = [w for w in host._rooms_list.winfo_children() if isinstance(w, tk.Frame)][-1]
label = row.winfo_children()[1]
top = canvas.yview()[0]
for _ in range(3):
    label.event_generate("<Button-5>")
root.update()
linux = canvas.yview()[0]
check("Button-5 on a row scrolls", linux > top, f"{top} -> {linux}")
for _ in range(2):
    label.event_generate("<MouseWheel>", delta=-120)
root.update()
check("MouseWheel on a row scrolls", canvas.yview()[0] > linux, f"{linux} -> {canvas.yview()[0]}")
scrolled = canvas.yview()[0]
tick(1.0)
tick(1.0)
check("scroll survives ticks", canvas.yview()[0] == scrolled, f"{scrolled} -> {canvas.yview()[0]}")
agents["orch-03"].status = "busy"
agents["orch-03"].last_seen = clock.now
tick(0.5)
check("rebuild on a status change", widgets() != before)
check("scroll survives a rebuild", abs(canvas.yview()[0] - scrolled) < 1e-6, f"{scrolled} -> {canvas.yview()[0]}")
root.destroy()
