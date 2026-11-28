"""ROOM-ALIGN evidence: the real Dungeon window under Xvfb on made-up data, one shot per standard room.

A main session (throne room), three simple sessions, the Apothecary with six idle avatars, the park and the pit.
No CLI starts, no git runs, no network; the data lives in a temp dir that is removed at the end.

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_room_align.py <out-dir>

Writes ``<room>.png`` (1366x768) for each room on the map.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="room-align-shot-"))
_DATA = _TMP / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageGrab  # noqa: E402

from bots.service import BotService  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import boss_view, cues, dungeon_nav, inside_roster, status_ink  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from routing import PointerGesture  # noqa: E402
from topics import ensure_topic, join_topic, set_topic  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

W, H = 1366, 768
SESSIONS = ((sr.MAIN, "moon-forge", "Moon forge"), (sr.SIMPLE, "glass-orchard", "Glass orchard"),
            (sr.SIMPLE, "ember-ledger", "Ember ledger"), (sr.SIMPLE, "salt-mill", "Salt mill"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "busy"), ("e5f6a7b8", "Vessa", "moon-forge", "thinking"),
          ("c9d0e1f2", "Pell", "glass-orchard", "busy"), ("d4e5f6a7", "Wren", "ember-ledger", "blocked"),
          ("f7a8b9c0", "Tamsin", "salt-mill", "error"),
          ("b1c2d3e4", "Quill", "", "idle"), ("b5c6d7e8", "Marrow", "", "idle"), ("b9c0d1e2", "Isolde", "", "idle"),
          ("b3c4d5e6", "Fenwick", "", "idle"), ("b7c8d9e0", "Juno", "", "idle"), ("b2c3d4e5", "Sorrel", "", "idle"))


class Stage:
    def __init__(self) -> None:
        _DATA.mkdir(parents=True)
        self.root = root = tk.Tk()
        host = self.host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host.config = {}
        host._config_path = _DATA / "config.json"
        host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        for kind, topic, name in SESSIONS:
            host._session_rooms.open(kind, "claude", topic)
            ensure_topic(_DATA, topic)
            set_topic(_DATA, topic, title=name, project=topic, status="open")
        now = time.time()
        self.agents = {}
        for aid, name, topic, status in AGENTS:
            if topic:
                join_topic(_DATA, topic, aid)
            self.agents[aid] = AgentInfo(aid, name, status=status, skin="caine", source="claude",
                                         project=topic or "errands", last_seen=now)
        for key, value in dict(_rooms_shown=True, _chat_shown=False, _rooms_btn=None, _chat_btn=None,
                               _rooms_sig=None, _rooms_thumbs={}, _rooms_warns={}, _bot_photos=[], _bot_vars=[],
                               _topics_stamp=None, sub_avatars={}, desktop_escape=False, bots=BotService(_DATA),
                               avatars={}, _gesture=PointerGesture(), _drag_av=None, _press_av=None,
                               _press_inside=None, _drag_off=(0, 0), _drag_prev=(0, 0),
                               render=SimpleNamespace(photos=PhotoCache())).items():
            setattr(host, key, value)
        host._chat_directory = lambda: _DATA
        host._select_topic = lambda topic: None
        host.scanner = SimpleNamespace(get_agents=lambda: dict(self.agents), bubbles=BubbleBoard(),
                                       _events=SimpleNamespace(data_dir=_DATA))
        host._inside = {aid: Avatar(a, 800, 600, 0, REGISTRY) for aid, a in self.agents.items()}
        view = self.view = host.dungeon = DungeonWindow(host)
        view.build(offscreen=True)
        root.deiconify()
        root.geometry(f"{W}x{H}+0+0")
        for _ in range(3):
            root.update()
        host._build_rooms_win()
        host._update_rooms_win(True)
        self.book = host.places = PlaceBook(host, path=None)
        self.book.attach()
        for aid in self.agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        inside_roster.hall(self.book)._talk = lambda: []
        self.scene = view.scene
        self.tick(1.0)
        boss = boss_view.view_for(self.book)
        if boss.chart_shown():  # the Friday burn-down covers the room
            boss.toggle_chart()

    def tick(self, seconds: float) -> None:
        end = time.time() + seconds
        while True:
            now = time.time()
            self.book._now = now
            self.book.draw_inside()
            status_ink.sweep(self.book)
            dungeon_nav.paint(self.book)
            self.root.update()
            if now >= end:
                return
            time.sleep(max(0.0, min(0.03, end - time.time())))

    def rooms(self) -> list[str]:
        layout = self.scene._rooms_painter.layout or {}
        names = [r["name"] for r in layout.get("rooms") or [] if isinstance(r, dict) and r.get("name")]
        return [n for n in names if not re.fullmatch(r"north|east|south|west|.*-\d+", n, re.I)]

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    cues.play = lambda _app, _name: None
    load_sprites(REGISTRY)
    stage = Stage()
    stage.tick(4.0)
    stage.scene._camera.zoom = 2
    for room in stage.rooms():
        if not dungeon_nav.jump(stage.host, room):
            continue
        stage.tick(1.6)
        name = re.sub(r"[^a-z0-9]+", "-", room.lower()).strip("-") or "room"
        stage.grab().save(out / f"{name}.png")
        print(name)
    stage.root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
