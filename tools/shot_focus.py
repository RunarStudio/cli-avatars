"""FOCUS evidence: pick a task, the other rooms go dark, an alert on another task waits, leave focus, it arrives.

Made-up rooms, sessions, cards and decisions in a temporary data folder; no real session, chat or board is read.
It draws the real Dungeon floor and the Needs you panel on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_focus.py <out-dir>

Writes ``focus.gif`` and ``desktop-1366.png``. ``seed_only`` gives the same data for a phone shot.
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

_DATA = Path(tempfile.mkdtemp(prefix="focus-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

import focus  # noqa: E402
from cli_avatars.app import focus_mode, focus_veil, inside_roster, needs_panel  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

W, H, DOCK = 1366, 768, 380
PROJECT = "lantern"
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "ember_mage", "busy"),
          ("e5f6a7b8", "Vessa", "glass-orchard", "frost_wanderer", "busy"),
          ("c9d0e1f2", "Quill", "ember-ledger", "ember_mage", "idle"))
CARDS = (("moon-forge", "Polish the moon gate", "doing"), ("glass-orchard", "Count the glass apples", "review"),
         ("ember-ledger", "Balance the ledger", "doing"))


def _seed(model) -> dict:
    reg = Registry(_DATA)
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    cards = {}
    for topic, title, column in CARDS:
        card = reg.task_create(PROJECT, title, topic=topic)
        reg.task_move(card["id"], column)
        cards[title] = card["id"]
    return cards


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [1_795_000_000.0]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        self.cards = _seed(self.model)
        agents = {aid: AgentInfo(aid, name, status=state, skin=skin, source="claude", project=project,
                                 last_seen=1_795_000_000.0) for aid, name, project, skin, state in AGENTS}
        self.dock = tk.Frame(root, bg="#141018", width=DOCK, height=H)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.canvas = tk.Canvas(root, width=W - DOCK, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in agents.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: agents),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: []
        hall._rooms = lambda: ([], [])
        self.app._needs_panel = needs_panel.NeedsPanel(self.dock, lambda _i: None, lambda _i: None)
        self.app._needs_panel.frame.pack(fill="both", expand=True)
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.tick(0.2)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.book.draw_inside()
        self.app._needs_gate = None
        focus_mode.step(self.app, force=True)
        needs_panel.step(self.app)

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w = 7 * len(text) + 24
    draw.rectangle((DOCK + 10, H - 40, DOCK + 10 + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((DOCK + 22, H - 33), text, fill=(240, 230, 200))
    return out


def desktop(stage: Stage, out: Path) -> None:
    frames = []

    def film(seconds: float, text: str, every: float = 0.2) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            frames.append(caption(stage.grab(), text))

    film(1.6, "Three rooms at work; nothing in focus")
    focus.start(_DATA, stage.cards["Polish the moon gate"])
    film(2.4, "Focus on 'Polish the moon gate' (card menu or F): Moon forge stays lit, the rest goes dark")
    ask_decision(_DATA, agent="claude:e5f6a7b8", room="glass-orchard", question="Keep the pear tree?",
                 options=["a=keep", "b=drop"], card=stage.cards["Count the glass apples"])
    film(2.8, "Vessa asks on another task: held, no sound, the seal counts 1 waiting")
    stage.grab().save(out / "desktop-1366.png")
    focus_veil.veil_for(stage.book)._leave(stage.canvas)
    film(2.8, "Leave focus: torches relight, the held decision arrives in Needs you (one cue)")
    frames[0].save(out / "focus.gif", save_all=True, append_images=frames[1:], duration=200, loop=0, optimize=True)


def seed_only() -> tuple[Path, dict]:
    """The made-up data alone, for a phone shot: serve it with ``webui.server``."""
    return _DATA, _seed(sr.SessionRooms(_DATA / "ui" / "session_rooms.json"))


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    try:
        load_sprites(REGISTRY)
        root = tk.Tk()
        root.geometry(f"{W}x{H}+0+0")
        stage = Stage(root)
        stage.tick(4.0)
        desktop(stage, out)
        root.destroy()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
