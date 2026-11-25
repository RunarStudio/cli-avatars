"""MESSENGER evidence: a made-up day on the Dungeon floor. Orrin's Moon forge decides silver rims and marks that it
affects the Glass orchard; a courier carries the scroll through the doors, a wax seal flashes, the orchard's card
lights up under its ribbon, and a click opens the decision with the reason.

Made-up rooms, cards and decisions in a temporary data folder; no real session, chat or board is read. It draws the
real Dungeon floor on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_courier.py <out-dir>

Writes ``messenger.gif`` and ``desktop-1366.png``. ``seed`` and ``decide`` give the same day to the phone shot.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="courier-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageGrab  # noqa: E402

from cli_avatars.app import courier_view, cues, inside_roster  # noqa: E402
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
from topics import join_topic, set_topic  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot_body import caption  # noqa: E402

W, H = 1366, 768
CROP = (300, 120, 1070, 600)
PROJECT = "lantern"
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge"), ("e5f6a7b8", "Vessa", "glass-orchard"),
          ("c9d0e1f2", "Pell", "ember-ledger"))


def seed(model) -> dict:
    """Rooms, members and one card per room; nothing decided yet."""
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    for aid, _name, topic in AGENTS:
        join_topic(_DATA, topic, aid)
    reg = Registry(_DATA)
    return {"forge": reg.task_create(PROJECT, "Forge the moon lantern", topic="moon-forge"),
            "orchard": reg.task_create(PROJECT, "Glass apple orchard", topic="glass-orchard"),
            "ledger": reg.task_create(PROJECT, "Ember ledger export", topic="ember-ledger")}


def decide(cards: dict) -> None:
    """Orrin asks, Daniel answers Silver and marks that it affects the Glass apple orchard."""
    row = ask_decision(_DATA, agent="a1b2c3d4", room="moon-forge", question="Silver or gold rims on the lantern?",
                       options=["a=Silver", "b=Gold"], card=cards["forge"]["id"])
    Registry(_DATA).decision_answer(row["id"], choice="a", text="affects Glass apple orchard: the apples hang in it")


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        self.cards = seed(self.model)
        self.agents = {aid: AgentInfo(aid, name, status="idle", skin="caine", source="claude", project=room,
                                      last_seen=self.clock[0] - 600) for aid, name, room in AGENTS}
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True)
                                  for aid, a in self.agents.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: self.agents),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _center="dungeon",
                                    show_center=lambda _name: None),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in self.agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        self.hall = inside_roster.hall(self.book)
        self.hall._talk = lambda: []
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.tick(0.2)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.book.draw_inside()
            self.root.update_idletasks()

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def film(stage: Stage, out: Path) -> None:
    frames = []
    view = courier_view.view_for(stage.book)

    def shoot(seconds: float, text: str, every: float = 0.15) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            shot = stage.grab().crop(CROP)
            shot = shot.resize((shot.width * 2, shot.height * 2), Image.NEAREST)
            frames.append(caption(shot, text).convert("P", palette=Image.ADAPTIVE, colors=160))

    shoot(1.2, "Three rooms at work; nothing decided yet")
    decide(stage.cards)
    view.reread()
    shoot(1.2, "Moon forge: Daniel picks Silver, 'affects Glass apple orchard'")
    while view.walk is not None and view.walk.done < 0.97:
        shoot(0.45, "A courier carries the sealed scroll through the doors")
    shoot(1.2, "Wax seal on arrival (stamp): the orchard's card lights up")
    view.reread()
    shoot(1.8, "NEW FROM MOON-FORGE glows until it is opened")
    key = next(iter(view.lit.values()))["key"]
    view.open(key)
    shoot(2.4, "Click the card or the ribbon: the decision and why it is news here")
    stage.grab().save(out / "desktop-1366.png")
    frames[0].save(out / "messenger.gif", save_all=True, append_images=frames[1:], duration=150, loop=0,
                   optimize=True)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    try:
        load_sprites(REGISTRY)
        cues.play = lambda _app, _name: None
        root = tk.Tk()
        root.geometry(f"{W}x{H}+0+0")
        stage = Stage(root)
        stage.tick(1.0)
        film(stage, out)
        root.destroy()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
