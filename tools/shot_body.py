"""BODY evidence: a made-up day on the Dungeon floor. Orrin strides, Vessa's card is blocked and she slumps on the
bench, Pell is asked a decision and taps his foot at the door, and the Moon forge's run passes 20 minutes and smokes.

Made-up rooms, sessions, a blocked card and an open decision in a temporary data folder; no real session, chat or
board is read. It draws the real Dungeon floor on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_body.py <out-dir>

Writes ``body-language.gif`` and ``desktop-1366.png``. ``seed`` and ``ROWS`` give the same day to the phone shot.
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

_DATA = Path(tempfile.mkdtemp(prefix="body-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from cli_avatars.app import body_view, cues, inside_roster  # noqa: E402
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

W, H = 1366, 768
CROP = (300, 120, 1070, 600)
PROJECT = "lantern"
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge"), ("e5f6a7b8", "Vessa", "glass-orchard"),
          ("c9d0e1f2", "Pell", "ember-ledger"))


def seed(model) -> None:
    """The rooms and their members; nothing waits yet."""
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    for aid, _name, topic in AGENTS:
        join_topic(_DATA, topic, aid)


def block() -> None:
    reg = Registry(_DATA)
    card = reg.task_create(PROJECT, "Count the glass apples", topic="glass-orchard")
    reg.task_move(card["id"], "doing")
    reg.task_move(card["id"], "blocked")


def ask() -> None:
    ask_decision(_DATA, agent="c9d0e1f2", room="ember-ledger", question="Copper or silver trim on the ledger?",
                 options=["a=Copper", "b=Silver"])


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        seed(self.model)
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
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True),
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

    def status(self, aid: str, state: str) -> None:
        self.agents[aid].status = state
        self.agents[aid].last_seen = self.clock[0]

    def reread(self) -> None:
        self.hall._read._ready = False
        body_view.view_for(self.book)._read._ready = False

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            for agent in self.agents.values():
                if agent.status == "busy":
                    agent.last_seen = self.clock[0]
            for aid, av in self.app._inside.items():
                av.agent = self.agents[aid]
            self.book.draw_inside()

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def hover(self, aid: str) -> None:
        av = self.app._inside[aid]
        view = body_view.view_for(self.book)
        view._motion(self.canvas, av.x + av.aw / 2, av.y + av.ah / 2)


def caption(image: Image.Image, text: str) -> Image.Image:
    from PIL import ImageFont

    out = image.copy()
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=22)
    w = int(draw.textlength(text, font=font)) + 32
    draw.rectangle((14, 14, 14 + w, 54), fill=(23, 16, 34), outline=(224, 170, 62), width=3)
    draw.text((30, 22), text, fill=(240, 230, 200), font=font)
    return out


def film(stage: Stage, out: Path) -> None:
    frames = []
    view = body_view.view_for(stage.book)

    def shoot(seconds: float, text: str, every: float = 0.2) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            shot = stage.grab().crop(CROP)
            shot = shot.resize((shot.width * 2, shot.height * 2), Image.NEAREST)
            frames.append(caption(shot, text).convert("P", palette=Image.ADAPTIVE, colors=160))

    shoot(1.6, "Morning: everyone idle, pacing their rooms")
    stage.status("a1b2c3d4", "busy")
    shoot(2.4, "Orrin starts working: flowing agents stride (lean, bob, dust at the heels)")
    block()
    stage.reread()
    shoot(4.0, "Vessa's card is blocked: she walks to the bench and slumps (sigh)")
    ask()
    stage.reread()
    shoot(4.0, "Pell is asked a decision: he waits at the door, tapping his foot (knock)")
    view.runs._start["a1b2c3d4"] = stage.clock[0] - 21 * 60
    shoot(2.4, "The Moon forge's run passes 20 min: its braziers smoke (crackle)")
    view.runs._start["a1b2c3d4"] = stage.clock[0] - 70 * 60
    shoot(2.4, "Past an hour the smoke runs thick")
    stage.hover("e5f6a7b8")
    shoot(1.6, "Hover an avatar: its state in one word")
    stage.grab().save(out / "desktop-1366.png")
    frames[0].save(out / "body-language.gif", save_all=True, append_images=frames[1:], duration=200, loop=0,
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
