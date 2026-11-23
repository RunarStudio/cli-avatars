"""Draw the Topics dock with the example roster and a few local status files.

No git fetch. The data directory is a temporary folder. Leave the window
up so a screenshot can be taken, then exit.

    python tools/shot_bot_groups.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="bot-groups-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from bots.service import BotService  # noqa: E402
from bots.status_source import SourceConfig  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app.dungeon_panes import repack  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed(service: BotService) -> None:
    service.import_example()
    service.save_source(SourceConfig(kind="folder", folder="status-local"))
    folder = _DATA / "bots" / "status-local" / "status"
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    plan = [
        ("busy", "drafting a note", now),
        ("thinking", "reading the board", now),
        ("waiting_on_user", "needs a look", now),
        ("busy", "still working", now - timedelta(hours=2)),
    ]
    for group, bots in service.sections():
        if group.name == "OCA":
            service.set_show(group.id, True)
            for (bot, _status), (state, line, moment) in zip(bots, plan):
                payload = {
                    "schema_version": 1,
                    "bot": bot.id,
                    "state": state,
                    "line": line,
                    "task_title": "Inbox triage",
                    "updated_at": _stamp(moment),
                }
                (folder / f"{bot.id}.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        if group.name == "Ungrouped":
            service.set_collapsed(group.id, True)
    service.poll()


def main() -> None:
    service = BotService(_DATA, runner=lambda *_args: 1)
    _seed(service)
    root = tk.Tk()
    root.title("Dungeon")
    host = OverlayApp.__new__(OverlayApp)
    host.root = root
    host.config = {}
    host._config_path = _DATA / "config.json"
    host._rooms_shown = True
    host._chat_shown = False
    host._rooms_btn = None
    host._chat_btn = None
    host._rooms_sig = None
    host._rooms_thumbs = {}
    host._rooms_warns = {}
    host._bot_photos = []
    host._bot_vars = []
    host._topics_stamp = None
    host.sub_avatars = {}
    host.bots = service
    host.desktop_escape = False
    host.scanner = SimpleNamespace(
        get_agents=lambda: {},
        bubbles=BubbleBoard(),
        _events=SimpleNamespace(data_dir=_DATA),
    )
    host.dungeon = DungeonWindow(host)
    host.dungeon.build(offscreen=True)
    host.dungeon._right_open = False
    host.dungeon._left.configure(width=480)
    repack(host.dungeon)
    root.deiconify()
    root.geometry("560x860+24+24")
    host._build_rooms_win()
    host._update_rooms_win(True)
    root.update_idletasks()
    root.update()
    print(f"READY {root.winfo_id()} {root.winfo_width()}x{root.winfo_height()}+{root.winfo_rootx()}+{root.winfo_rooty()}", flush=True)
    root.after(12000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
