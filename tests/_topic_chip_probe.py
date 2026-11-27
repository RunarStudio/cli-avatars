"""Child process for ``test_topic_chip``: a topic card's status chip is never clipped in the Topics dock.

    python tests/_topic_chip_probe.py <repo root> <temp dir>

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
from cli_avatars.app import rooms_panel  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from topics import ensure_topic, join_topic, set_topic, status_label  # noqa: E402

NOW = 1_795_000_000.0
rooms_panel.time = SimpleNamespace(time=lambda: NOW)
DATA = Path(sys.argv[2])
TITLES = {"moon-forge": "Moon forge", "ember-vault": "Ember vault of the long winter night"}
agents = {
    f"a{i}": SimpleNamespace(agent_id=f"a{i}", name=f"Fern-{i}", status="busy", source="claude", project="moon-forge",
                             parent_id=None, last_seen=NOW - 5, skin="caine", is_demo=False, failed=False,
                             subagents=0)
    for i in range(3)
}
for topic, title in TITLES.items():
    ensure_topic(DATA, topic)
    set_topic(DATA, topic, title=title, project="moon-forge", status="open")
    for aid in agents:
        join_topic(DATA, topic, aid)
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
root.geometry("1366x768+20000+20000")
root.deiconify()
host._build_rooms_win()
host._update_rooms_win(True)
for _ in range(3):
    root.update()


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def labels(text: str) -> list:
    found, todo = [], [host._rooms_list]
    while todo:
        for child in todo.pop().winfo_children():
            todo.append(child)
            if isinstance(child, tk.Label) and child.cget("text") == text:
                found.append(child)
    return found


chips = labels(status_label("open"))
check("two topic chips", len(chips) == 2, str(len(chips)))
for chip in chips:
    card = chip.master.master.master
    inside = chip.winfo_rootx() + chip.winfo_width() <= card.winfo_rootx() + card.winfo_width()
    check("chip whole and inside its card", chip.winfo_width() >= chip.winfo_reqwidth() and inside,
          f"{chip.winfo_width()} of {chip.winfo_reqwidth()} px, card right {card.winfo_rootx() + card.winfo_width()}")
root.destroy()
