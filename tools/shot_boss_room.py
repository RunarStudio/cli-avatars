"""BOSS-ROOM.1 evidence: made-up weeks in the Oni Pit and the Crypt. An empty small pit; blocked lantern tasks pile up,
the oni grows and its room slides wider; weeks pass and stale tasks drop into the Crypt as skulls; tasks close, the
oni takes the hits and the room shrinks back.

Made-up cards in a temporary data folder; no real session, chat or board is read. It draws the real Dungeon floor
on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_boss_room.py <out-dir>

Writes ``boss-room.gif``, ``empty.png`` and ``desktop-1366.png``.
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

_DATA = Path(tempfile.mkdtemp(prefix="boss-room-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageGrab  # noqa: E402

from cli_avatars.app import boss_rooms, boss_view, crypt_view, cues, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_camera import Camera  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot_body import caption  # noqa: E402

W, H = 1366, 768
PROJECT, TOPIC = "lantern", "moon-forge"
PARTS = ("wick", "glass", "rim", "hinge", "chain", "oil cap", "handle", "shade", "base", "vent", "hook")
DAY = 86400.0


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        set_topic(_DATA, TOPIC, title="Moon forge", project=PROJECT, status="open")
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        self.canvas._camera = Camera(zoom=2)
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={}, _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: {}),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _center="dungeon",
                                    show_center=lambda _name: None),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        self.hall = inside_roster.hall(self.book)
        self.hall._talk = lambda: []
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.view = boss_view.view_for(self.book)
        self.crypt = crypt_view.view_for(self.book)
        self.view.chart_on = (time.strftime("%Y-%m-%d"), False)
        self.tick(0.2)
        self.frame()

    def frame(self) -> None:
        """Pan so the space between the two rooms at their largest sits mid-screen."""
        painter, plan = self.canvas._rooms_painter, self.hall.plan()
        pit, crypt = plan.floor(boss_rooms.PIT), plan.floor(boss_rooms.CRYPT)
        u, v = (pit.u0 + crypt.u0 + 6) / 2.0, (pit.v0 + crypt.v0 + 8) / 2.0
        x, y = painter.to_canvas(u, v)
        cam = self.canvas._camera
        cam.pan = (round(cam.pan[0] - (x - W / 2)), round(cam.pan[1] - (y - H / 2) + 40))
        painter.paint(self.canvas)
        self.tick(0.1)

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
    view, reg = stage.view, Registry(_DATA)
    made: list[dict] = []

    def shoot(seconds: float, text: str, every: float = 0.15) -> None:
        for _ in range(max(1, round(seconds / every))):
            stage.tick(every)
            shot = stage.grab().crop((143, 104, 143 + 1080, 104 + 560))
            frames.append(caption(shot, text).convert("P", palette=Image.ADAPTIVE, colors=200))

    def pile(count: int) -> None:
        for _ in range(count):
            n = len(made)
            card = reg.task_create(PROJECT, f"Lantern {PARTS[n % len(PARTS)]} #{n + 1}", topic=TOPIC)
            reg.task_move(card["id"], "blocked")
            made.append(card)
        view.reread()

    shoot(1.5, "No backlog: the Oni Pit is small and bare, the Crypt empty")
    stage.grab().save(out / "empty.png")
    pile(4)
    shoot(2.0, "Week 1: 4 blocked tasks: a ko-oni, its room slides wider (dust, grind)")
    pile(8)
    shoot(2.0, "12 feed it: aka-oni, the room grows a step")
    pile(21)
    shoot(2.4, "33: the dai-oni fills the biggest pit")
    for days, text in ((12, "Weeks pass, nothing moves..."), (19, "Day 31: stale tasks drop into the Crypt")):
        stage.clock[0] += days * DAY
        view.reread()
        shoot(2.2 if days > 12 else 1.0, text)
    stage.crypt._hover(made[5]["id"])
    shoot(1.6, "Hover a skull: its task and how long it was forgotten")
    stage.grab().save(out / "desktop-1366.png")
    stage.crypt._hover(None, made[5]["id"])
    for card in made[:20]:
        reg.task_move(card["id"], "done")
    view.reread()
    while len(view.hits) > 2:
        stage.tick(0.2)
    shoot(2.0, "Tasks close: hits, skulls leave, both rooms shrink", every=0.1)
    for card in made[20:]:
        reg.task_move(card["id"], "done")
    view.reread()
    while len(view.hits) > 1:
        stage.tick(0.2)
    while view.hits or view.hit is not None:
        shoot(0.3, "The last hit knocks it out (fanfare)", every=0.1)
    shoot(boss_view.DOWN_S + 1.2, "HP 0: back to a small, empty room")
    frames[0].save(out / "boss-room.gif", save_all=True, append_images=frames[1:], duration=120, loop=0,
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
        stage.tick(0.5)
        film(stage, out)
        root.destroy()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
