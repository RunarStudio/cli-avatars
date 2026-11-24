"""Show the Dungeon's Throne tab with made-up agents and a made-up board.

The data directory is a temporary folder; no real session or board is read.
Leave the window up so a screenshot can be taken, then exit.

    python tools/shot_throne_room.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="throne-room-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from board.model import new_card  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from board.store import LocalStore  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402

PROJECT = "keep"
AGENTS = (
    ("a0", "Warden", None, "ember_mage", "busy"),
    ("a1", "Ash", None, "forest_scout", "thinking"),
    ("a2", "Flint", None, "frost_wanderer", "blocked"),
    ("s0", "", "a0", "little_grok", "idle"),
    ("s1", "", "a1", "imp", "busy"),
    ("s2", "", "a2", "mini_drone", "busy"),
)
CARDS = (
    ("todo", "Count barrels", None, 0), ("todo", "Feed the imps", None, 0),
    ("todo", "Forge new key", "flint", 0), ("todo", "Map the vault", "ash", 0),
    ("doing", "Brew reports", "ash", 80), ("doing", "Mend the gate", "flint", 35),
    ("doing", "Light beacons", "warden", 60),
    ("review", "Bridge check", "moss", 100), ("review", "Rune spelling", "ash", 100),
    ("done", "Oil hinges", "moss", 100), ("done", "Name the cat", "warden", 100),
    ("done", "Stack scrolls", "imp", 100), ("done", "Sweep the hall", "imp", 100),
    ("blocked", "Dragon asleep", "flint", 20),
)


def _seed() -> None:
    store = LocalStore()
    for column, title, who, progress in CARDS:
        card = new_card(PROJECT, title, assignee=who)
        store.put({**card, "column": column, "progress": progress})


def _agents() -> dict:
    return {
        aid: AgentInfo(agent_id=aid, name=name, parent_id=parent, skin=skin, status=state,
                       project=PROJECT, is_demo=True, source="demo")
        for aid, name, parent, skin, state in AGENTS
    }


def main() -> None:
    _seed()
    load_sprites(REGISTRY)
    root = tk.Tk()
    host = OverlayApp.__new__(OverlayApp)
    host.root = root
    host.config = {}
    host._config_path = _DATA / "config.json"
    host._rooms_shown = False
    host._chat_shown = False
    host._rooms_btn = None
    host._chat_btn = None
    host.desktop_escape = False
    host.bots = None
    host._rooms_sig = None
    host._rooms_thumbs = {}
    host._rooms_warns = {}
    host._bot_photos = []
    host._bot_vars = []
    host._topics_stamp = None
    host.sub_avatars = {}
    host.scanner = SimpleNamespace(
        get_agents=_agents,
        bubbles=BubbleBoard(),
        _events=SimpleNamespace(data_dir=_DATA),
    )
    host.dungeon = DungeonWindow(host)
    host.dungeon.build(offscreen=True)
    host.dungeon._right_open = False
    host.dungeon.set_left(False)
    root.deiconify()
    root.geometry(sys.argv[1] if len(sys.argv) > 1 else "1560x1000+0+0")
    host.dungeon.show_center("throne")
    root.update()
    print(f"READY {root.winfo_id()}", flush=True)
    root.after(15000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
