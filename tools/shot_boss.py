"""BACKLOG-BOSS evidence: a made-up week in the Pit. Blocked lantern tasks pile up and the oni grows a stage at a
time (it roars); hover lists what feeds it; closed tasks hit it (flash, shake, -1, the bar drops); Friday shows the
HP bar and the week's burn-down; closing the rest knocks it out.

Made-up cards in a temporary data folder, with Monday to Thursday's HP written into its ``boss.json``; no real
session, chat or board is read. It draws the real Dungeon floor on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_boss.py <out-dir>

Writes ``boss.gif`` and ``desktop-1366.png``. ``seed_week`` gives the same week to the phone shot.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="boss-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageGrab  # noqa: E402

import backlog_boss  # noqa: E402
from cli_avatars.app import boss_view, cues, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot_body import caption  # noqa: E402

W, H = 1366, 768
PROJECT = "lantern"
TOPIC = "moon-forge"
PARTS = ("wick", "glass", "rim", "hinge", "chain", "oil cap", "handle", "shade", "base", "vent", "hook")
WEEK = {0: 4, 1: 12, 2: 33, 3: 27}


def friday(now: float) -> float:
    """Ten in the morning on the Friday of ``now``'s week (or the next one on a weekend)."""
    day = datetime.fromtimestamp(now).replace(hour=10, minute=0, second=0, microsecond=0)
    return (day + timedelta(days=(4 - day.weekday()) % 7)).timestamp()


def seed_week(directory: Path, today: date) -> None:
    """Monday to Thursday's HP of ``today``'s week in the boss store (made-up)."""
    monday = today - timedelta(days=today.weekday())
    days = {(monday + timedelta(days=n)).isoformat(): hp for n, hp in WEEK.items()}
    (directory / backlog_boss.STORE_NAME).write_text(json.dumps({"feeding": [], "hit": {}, "days": days}),
                                                     encoding="utf-8")


def pile(reg: Registry, count: int, start: int) -> list[dict]:
    """``count`` made-up blocked lantern tasks."""
    out = []
    for n in range(start, start + count):
        card = reg.task_create(PROJECT, f"Lantern {PARTS[n % len(PARTS)]} #{n + 1}", topic=TOPIC)
        reg.task_move(card["id"], "blocked")
        out.append(card)
    return out


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [friday(time.time())]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        set_topic(_DATA, TOPIC, title="Moon forge", project=PROJECT, status="open")
        seed_week(_DATA, datetime.fromtimestamp(self.clock[0]).date())
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
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
        self.view.chart_on = (datetime.fromtimestamp(self.clock[0]).date().isoformat(), False)
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
    view, reg = stage.view, Registry(_DATA)
    crop = [None]

    def shoot(seconds: float, text: str, every: float = 0.15) -> None:
        for _ in range(max(1, round(seconds / every))):
            stage.tick(every)
            shot = stage.grab()
            if crop[0] is None:
                x, y = stage.canvas._rooms_painter.to_canvas(*boss_view.pit_spot(stage.hall.plan()))
                left, top = max(0, min(W - 1080, int(x) - 810)), max(0, min(H - 560, int(y) - 440))
                crop[0] = (left, top, left + 1080, top + 560)
            shot = shot.crop(crop[0])
            frames.append(caption(shot, text).convert("P", palette=Image.ADAPTIVE, colors=180))

    def read() -> None:
        view.reread()
        stage.tick(0.1)

    cards = pile(reg, 4, 0)
    read()
    shoot(1.5, "Mon: 4 blocked tasks feed a dozing ko-oni in the Pit")
    cards += pile(reg, 8, 4)
    read()
    shoot(1.8, "Tue: the backlog piles up to 12: it grows (roar)")
    cards += pile(reg, 21, 12)
    read()
    shoot(1.8, "Wed: 33 blocked or overdue: the dai-oni")
    view._hover(True)
    shoot(1.8, "Hover: its HP and the tasks that feed it")
    view._hover(False)
    for card in cards[:6]:
        reg.task_move(card["id"], "done")
    read()
    while view.hits or view.hit is not None:
        shoot(0.3, "Thu: each closed task hits it: flash, shake, -1, HP drops", every=0.1)
    shoot(0.9, "Thu: 27 left: back to an oni taisho")
    view.toggle_chart()
    shoot(2.6, "Fri: the HP bar and the week's burn-down")
    stage.grab().save(out / "desktop-1366.png")
    view.toggle_chart()
    for card in cards[6:]:
        reg.task_move(card["id"], "done")
    read()
    while len(view.hits) > 1:
        stage.tick(0.2)
    while view.hits or view.hit is not None:
        shoot(0.3, "Closing the rest: the last hit knocks it out (fanfare)", every=0.1)
    shoot(2.0, "HP 0: defeated")
    frames[0].save(out / "boss.gif", save_all=True, append_images=frames[1:], duration=120, loop=0, optimize=True)


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
