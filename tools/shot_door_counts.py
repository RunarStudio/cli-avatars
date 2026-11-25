"""DOOR-COUNTS evidence: door plaques on the Dungeon floor, the Topics strip, and the phone map.

Made-up rooms, sessions, cards and decisions in a temporary data folder; no real session, chat or board is
read. It draws the real Dungeon floor on a Tk canvas and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_door_counts.py <out-dir>

Writes ``doors.gif`` (a decision arrives, the plaque takes the seal, hover shows the breakdown) and
``desktop-1366.png``. ``seed_only`` gives the same data for a phone shot of ``webui.server``.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="door-counts-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from cli_avatars.app import door_plaque, door_totals, inside_roster, orch_dock  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.app.throttle import StoreThrottle  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.task_chats import start_chat  # noqa: E402
from topics import set_topic  # noqa: E402

W, H, DOCK = 1366, 768, 380
PROJECT = "lantern"
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (
    ("a1b2c3d4", "Orrin", "moon-forge", "ember_mage", "busy", None, 0),
    ("a1b2c3d5", "Wren", "moon-forge", "forest_scout", "thinking", "a1b2c3d4", 1),
    ("e5f6a7b8", "Vessa", "glass-orchard", "frost_wanderer", "busy", None, 0),
    ("c9d0e1f2", "Quill", "ember-ledger", "ember_mage", "idle", None, 2),
)
CARDS = (("moon-forge", "Polish the moon gate", "doing", 2), ("moon-forge", "Forge three silver keys", "todo", 0),
         ("glass-orchard", "Count the glass apples", "review", 1), ("ember-ledger", "Balance the ledger", "doing", 1))


def _seed(model) -> None:
    reg = Registry(_DATA)
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    set_topic(_DATA, "sand-clock", title="Sand clock", project="dunes", status="open")
    for topic, title, column, chats in CARDS:
        card = reg.task_create(PROJECT, title, topic=topic)
        if column != "todo":
            reg.task_move(card["id"], column)
        for _ in range(chats):
            start_chat(reg, card["id"], "claude")
    ask_decision(_DATA, agent="claude:a1b2c3d4", room="moon-forge", question="Oak or ash for the gate?",
                 options=["a=oak", "b=ash"])


def _sessions() -> dict:
    return {aid: AgentInfo(aid, name, status=state, skin=skin, source="claude", project=project, parent_id=parent,
                           subagents=subs, last_seen=1_795_000_000.0)
            for aid, name, project, skin, state, parent, subs in AGENTS}


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [1_795_000_000.0]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        _seed(self.model)
        self.agents = _sessions()
        self.dock = tk.Frame(root, bg="#0d0d1a", width=DOCK, height=H)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.canvas = tk.Canvas(root, width=W - DOCK, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        tops = {aid: a for aid, a in self.agents.items() if not a.parent_id}
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in tops.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: self.agents),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in tops:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: []
        hall._rooms = lambda: ([], [])
        filler = tk.Frame(self.dock, bg="#0d0d1a")
        filler.pack(fill="both", expand=True)
        self.strip = door_totals.attach(self.app, self.dock, filler)
        self.strip._read = StoreThrottle(0.0)
        orch_dock.render(self.app, filler, orch_dock.rows(self.app))
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.tick(0.2)
        self.plaques = door_plaque.plaques_for(self.book)
        self.plaques._read = StoreThrottle(0.0)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.book.draw_inside()
        self.strip.refresh(self.app)

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w = 7 * len(text) + 24
    x = DOCK + 10
    draw.rectangle((x, 10, x + w, 36), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((x + 12, 17), text, fill=(240, 230, 200))
    return out


def desktop(stage: Stage, out: Path) -> None:
    frames = []

    def film(seconds: float, text: str, every: float = 0.2) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            frames.append(caption(stage.grab(), text))

    film(2.4, "Door plaques: orchestrators, agents, subagents, chats, open topics")
    ask_decision(_DATA, agent="claude:e5f6a7b8", room="glass-orchard", question="Keep the pear?",
                 options=["a=keep", "b=drop"])
    film(2.4, "Vessa asks a decision: Glass orchard's plaque takes a red seal")
    stage.plaques.show(stage.canvas, "glass-orchard")
    film(3.0, "Hover the plaque: the full breakdown")
    stage.plaques.leave(stage.canvas, "glass-orchard")
    film(1.0, "Behind the doors: total and each project, top of Topics")
    frames[0].save(out / "doors.gif", save_all=True, append_images=frames[1:], duration=200, loop=0, optimize=True)
    stage.plaques.show(stage.canvas, "moon-forge")
    stage.tick(0.2)
    stage.grab().save(out / "desktop-1366.png")


def seed_only() -> Path:
    """The made-up data alone, for a phone shot: serve it with ``webui.server`` and ``webui.demo.SESSIONS``."""
    _seed(sr.SessionRooms(_DATA / "ui" / "session_rooms.json"))
    return _DATA


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    try:
        load_sprites(REGISTRY)
        root = tk.Tk()
        root.geometry(f"{W}x{H}+0+0")
        stage = Stage(root)
        stage.tick(6.0)
        desktop(stage, out)
        root.destroy()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
