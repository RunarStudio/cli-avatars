"""PARK.1 + IDLE-PROPS.1 evidence: a made-up evening on the Dungeon floor. The rooms come alive (hands warmed at the
hearth, dice, a book, the cat fed), then the work is done and the bots walk out to the park to sit and train under the
lanterns, until one is called back to its room by a new card.

Made-up rooms, sessions and cards in ``CLI_AVATARS_DATA_DIR`` (your own temp dir, required); no real session, chat
or board is read and no CLI runs. It draws the real Dungeon floor on Tk and grabs the screen, so run it under Xvfb:

    CLI_AVATARS_DATA_DIR=<temp dir> xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_park.py <out-dir>

Writes ``idle.gif``, ``park.gif`` and ``desktop-1366.png``. ``seed`` gives the same evening to the phone shot.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if not os.environ.get("CLI_AVATARS_DATA_DIR"):
    raise SystemExit(__doc__)
_DATA = Path(os.environ["CLI_AVATARS_DATA_DIR"])

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageFont, ImageGrab  # noqa: E402

from cli_avatars.app import body_view, cues, inside_roster, life_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

W, H = 1366, 768
PROJECT = "lantern"
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "caine"), ("e5f6a7b8", "Vessa", "glass-orchard", "forest_scout"),
          ("c9d0e1f2", "Pell", "ember-ledger", "frost_wanderer"), ("d4e5f6a7", "Wren", "", "ember_mage"),
          ("f7a8b9c0", "Tamsin", "", "bubble"))
CARDS = (("Polish the moon lens", "moon-forge", "doing"), ("Sort the glass seeds", "glass-orchard", "doing"),
         ("Mend the orchard gate", "glass-orchard", "todo"), ("Tally the embers", "ember-ledger", "todo"),
         ("Seal the ledger", "ember-ledger", "doing"))


def seed(model) -> None:
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    for aid, _name, topic, _skin in AGENTS:
        if topic:
            join_topic(_DATA, topic, aid)
    reg = Registry(_DATA)
    for title, topic, column in CARDS:
        card = reg.task_create(PROJECT, title, topic=topic)
        if column != "todo":
            reg.task_move(card["id"], "doing")


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        seed(self.model)
        self.agents = {aid: AgentInfo(aid, name, status="busy", skin=skin, source="claude", project=room or "errands",
                                      last_seen=self.clock[0]) for aid, name, room, skin in AGENTS}
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

    def quiet(self, aid: str, seconds: float) -> None:
        self.agents[aid].status = "idle"
        self.agents[aid].last_seen = self.clock[0] - seconds

    def busy(self, aid: str) -> None:
        self.agents[aid].status = "busy"
        self.agents[aid].last_seen = self.clock[0]

    def reread(self) -> None:
        self.hall._read._ready = False
        body_view.view_for(self.book)._read._ready = False
        life_view.view_for(self.book)._read._ready = False

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            for agent in self.agents.values():
                if agent.status == "busy":
                    agent.last_seen = self.clock[0]
            self.book.draw_inside()

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def box(self, rooms: tuple[str, ...], pad: int = 26) -> tuple[int, int, int, int]:
        """Canvas box around ``rooms`` (their floors plus the wall height)."""
        painter = self.canvas._rooms_painter
        xs, ys = [], []
        for room in (painter.layout or {}).get("rooms") or []:
            if room.get("name") in rooms:
                (u, v), (w, h) = room["origin"], room["size"]
                for a, b in ((u, v), (u + w, v), (u + w, v + h), (u, v + h)):
                    x, y = painter.to_canvas(a, b)
                    xs.append(x)
                    ys.append(y)
        top = min(ys) - 48 * painter._scale
        return (max(0, int(min(xs)) - pad), max(0, int(top) - pad), min(W, int(max(xs)) + pad),
                min(H, int(max(ys)) + pad))


WORDS = {"warm": "warms her hands at the hearth", "dice": "rolls dice", "drink": "drinks at the well",
         "read": "reads at the lectern", "polish": "polishes the rack", "feed": "feeds the cat", "sit": "sits on a bench",
         "hit": "hits a dummy", "lift": "lifts", "spar": "spars at the post", "stroll": "strolls the loop"}


def doing(stage: Stage, aids) -> str:
    """What each of ``aids`` does now, from the live holds."""
    holds = life_view.view_for(stage.book).holds
    names = {aid: name for aid, name, _room, _skin in AGENTS}
    return ", ".join(f"{names[a]} {WORDS[holds[a].act]}" for a in aids if a in holds)


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=20)
    w = int(draw.textlength(text, font=font)) + 28
    draw.rectangle((12, 12, 12 + w, 48), fill=(23, 16, 34), outline=(224, 170, 62), width=3)
    draw.text((26, 19), text, fill=(240, 230, 200), font=font)
    return out


class Reel:
    def __init__(self, stage: Stage, crop: tuple[int, int, int, int], zoom: int) -> None:
        self.stage, self.crop, self.zoom, self.frames = stage, crop, zoom, []

    def shoot(self, seconds: float, text: str, every: float = 0.2) -> None:
        for _ in range(max(1, round(seconds / every))):
            self.stage.tick(every)
            shot = self.stage.grab().crop(self.crop)
            shot = shot.resize((shot.width * self.zoom, shot.height * self.zoom), Image.NEAREST)
            self.frames.append(caption(shot, text).convert("P", palette=Image.ADAPTIVE, colors=192))

    def save(self, path: Path) -> None:
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:], duration=200, loop=0, optimize=True)


def film_idle(stage: Stage, out: Path) -> None:
    reel = Reel(stage, stage.box((sr.APOTHECARY, "moon-forge", "glass-orchard", "ember-ledger")), 2)
    reel.shoot(1.6, "Everyone at work: each room's task table holds its doing and todo cards")
    stage.quiet("d4e5f6a7", 70)
    stage.quiet("f7a8b9c0", 75)
    stage.tick(0.1)
    reel.shoot(5.0, "Quiet a minute: " + doing(stage, ("d4e5f6a7", "f7a8b9c0")))
    for aid in ("a1b2c3d4", "e5f6a7b8", "c9d0e1f2"):
        stage.quiet(aid, 70)
    stage.tick(0.1)
    reel.shoot(6.0, doing(stage, ("a1b2c3d4", "e5f6a7b8", "c9d0e1f2")) + "; each object moves while used")
    stage.quiet("d4e5f6a7", 700)
    reel.shoot(8.0, "Ten quiet minutes: Wren leaves for the park, through the doors")
    reel.save(out / "idle.gif")


def film_park(stage: Stage, out: Path) -> None:
    for aid in stage.agents:
        stage.busy(aid)
    stage.tick(8.0)
    reel = Reel(stage, stage.box((sr.APOTHECARY, "Park")), 2)
    reel.shoot(1.6, "Night in the park: lanterns, fireflies, the obelisk's runes")
    for i, aid in enumerate(("a1b2c3d4", "e5f6a7b8", "c9d0e1f2", "f7a8b9c0")):
        stage.quiet(aid, 700 + i)
    reel.shoot(12.0, "The work is done: after 10 quiet minutes the bots walk out to the park")
    reel.shoot(5.0, doing(stage, ("a1b2c3d4", "e5f6a7b8", "c9d0e1f2", "f7a8b9c0")))
    stage.canvas.update()
    stage.grab().save(out / "desktop-1366.png")
    reg = Registry(_DATA)
    card = reg.task_create(PROJECT, "Recast the moon lens", topic="moon-forge", assignee="a1b2c3d4")
    reg.task_move(card["id"], "doing")
    stage.busy("a1b2c3d4")
    stage.reread()
    reel.shoot(6.0, "A new card for Orrin: he gets up and walks back to the Moon forge")
    reel.save(out / "park.gif")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    load_sprites(REGISTRY)
    cues.play = lambda _app, _name: None
    root = tk.Tk()
    root.geometry(f"{W}x{H}+0+0")
    stage = Stage(root)
    stage.tick(1.0)
    film_idle(stage, out)
    film_park(stage, out)
    root.destroy()
    print("wrote idle.gif, park.gif, desktop-1366.png")


if __name__ == "__main__":
    main()
