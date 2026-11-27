"""Child process for ``test_dock_dots``: every state dot in the Topics dock reads the one palette (``status_ink``).

    python tests/_dock_dots_probe.py <repo root> <temp dir>

Prints ``ok <check>`` per check; any failed check exits 1. Exit 77 when Tk has no display.
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
from cli_avatars.app import rooms_panel, status_ink  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from topics import ensure_topic, join_topic  # noqa: E402

NOW = 1_795_000_000.0
rooms_panel.time = SimpleNamespace(time=lambda: NOW)
DATA = Path(sys.argv[2])
STATES = ("busy", "thinking", "subagent", "blocked")
agents = {
    f"a{i}": SimpleNamespace(agent_id=f"a{i}", name=f"Fern-{i}", status=state, source="claude", project="moon-forge",
                             parent_id=None, last_seen=NOW - 5, skin="caine", is_demo=False, failed=False,
                             subagents=0)
    for i, state in enumerate(STATES)
}
ensure_topic(DATA, "moon-forge")
for aid in agents:
    join_topic(DATA, "moon-forge", aid)
host = OverlayApp.__new__(OverlayApp)
host.root = root
host.config = {}
host._config_path = DATA / "config.json"
for key, value in dict(_rooms_shown=True, _chat_shown=False, _rooms_btn=None, _chat_btn=None, _rooms_sig=None,
                       _rooms_thumbs={}, _rooms_warns={}, _bot_photos=[], _bot_vars=[], _topics_stamp=None,
                       sub_avatars={}, desktop_escape=False).items():
    setattr(host, key, value)
host.scanner = SimpleNamespace(get_agents=lambda: agents, bubbles=BubbleBoard(),
                               _events=SimpleNamespace(data_dir=DATA))
host.dungeon = DungeonWindow(host)
host.dungeon.build(offscreen=True)
root.geometry("640x480+20000+20000")
root.deiconify()
host._build_rooms_win()
host._update_rooms_win(True)
root.update()


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def dots() -> list:
    found, todo = [], [host._rooms_list]
    while todo:
        for child in todo.pop().winfo_children():
            todo.append(child)
            if isinstance(child, tk.Label) and child.cget("text") == "●":
                found.append(child.cget("fg").lower())
    return found


shown = dots()
want = {status_ink.colour(state).lower() for state in STATES}
check("every state has its palette dot", want <= set(shown), f"{sorted(want - set(shown))} missing in {shown}")
check("no dot outside the palette", set(shown) <= {c.lower() for c in status_ink.PALETTE.values()}, str(shown))
root.destroy()
