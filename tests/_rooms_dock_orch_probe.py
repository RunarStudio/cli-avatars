"""Child process for ``test_rooms_dock``: the Topics dock with an orchestrator room, bots and open decisions.

    python tests/_rooms_dock_orch_probe.py <repo root> <temp dir>

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

from bots.service import BotService  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import orch_dock, rooms_panel, session_rooms  # noqa: E402
from cli_avatars.app.dungeon_panes import repack  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from decisions import ask_decision  # noqa: E402
from topics import ensure_topic  # noqa: E402

NOW = 1_795_000_000.0
clock = SimpleNamespace(now=NOW)
fake = SimpleNamespace(time=lambda: clock.now)
rooms_panel.time = fake
orch_dock.time = fake
DATA = Path(sys.argv[2])
for topic in ("general", "lantern-notes"):
    ensure_topic(DATA, topic)
ask_decision(DATA, agent="claude:a1b2c3d4", room="general", question="Paint the door?", options=["a=yes", "b=no"])
agents = {
    "lord": SimpleNamespace(agent_id="lord", name="Orrin", status="idle", source="claude", project="harbor-map",
                            parent_id=None, last_seen=NOW - 90, skin="caine", is_demo=False, failed=False,
                            subagents=0),
    "solo": SimpleNamespace(agent_id="solo", name="Wren", status="busy", source="claude", project="",
                            parent_id=None, last_seen=NOW, skin="caine", is_demo=False, failed=False, subagents=0),
}
bots = BotService(DATA)
bots.import_example()
host = OverlayApp.__new__(OverlayApp)
host.root = root
host.config = {}
host._config_path = DATA / "config.json"
for key, value in dict(_rooms_shown=True, _chat_shown=False, _rooms_btn=None, _chat_btn=None, _rooms_sig=None,
                       _rooms_thumbs={}, _rooms_warns={}, _bot_photos=[], _bot_vars=[], _topics_stamp=None,
                       sub_avatars={}, desktop_escape=False, bots=bots).items():
    setattr(host, key, value)
host.scanner = SimpleNamespace(get_agents=lambda: agents, bubbles=BubbleBoard(),
                               _events=SimpleNamespace(data_dir=DATA))
host.dungeon = DungeonWindow(host)
host.dungeon.build(offscreen=True)
host._session_rooms = session_rooms.SessionRooms(None)
opened = host._session_rooms.open("simple", "claude", "harbor-map")
repack(host.dungeon)
root.geometry("640x480+20000+20000")
root.deiconify()
host._build_rooms_win()
host._update_rooms_win(True)
root.update()
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
    return [root.nametowidget(name).cget("text") for name in sorted(widgets())
            if isinstance(root.nametowidget(name), tk.Label)]


shown = texts()
check("orch row, bots and decisions present",
      opened == "" and "seen 1m ago" in shown and "Bots" in shown and "decisions 1" in shown, str(shown[:12]))
before = widgets()
for _ in range(360):
    agents["solo"].last_seen = clock.now
    clock.now += 0.5
    panel.refresh()
    root.update()
check("180 s of ticks keep every widget", widgets() == before, f"{len(before - widgets())} replaced")
check("orch age text moves", "seen 4m ago" in texts(), str([t for t in texts() if "ago" in t]))
agents["lord"].name = "Orrin II"
clock.now += 0.5
panel.refresh()
root.update()
check("rebuild on an orch row change", widgets() != before and "Orrin II · harbor-map · Claude" in texts())
root.destroy()
