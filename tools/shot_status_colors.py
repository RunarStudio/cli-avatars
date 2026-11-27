"""STATUSCOLOR evidence: the real Dungeon window under Xvfb on made-up data, four avatars cycling their states.

Each nameplate's status word takes its state colour and pulses once on a change. No CLI starts, no git runs, no
network.

    xvfb-run -a -s "-screen 0 1600x900x24" python tools/shot_status_colors.py <out-dir>

Writes ``status-colors.gif`` and ``status-1366.png``.
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

_TMP = Path(tempfile.mkdtemp(prefix="status-shot-"))
_DATA = _TMP / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageFont, ImageGrab  # noqa: E402

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
from cli_avatars.world.avatar import Avatar  # noqa: E402
from routing import PointerGesture  # noqa: E402
from topics import ensure_topic, join_topic, set_topic  # noqa: E402

W, H = 1366, 768
STEP = 0.1
CYCLE = ("idle", "busy", "thinking", "subagent", "blocked", "error")
AGENTS = (("a1b2c3d4", "Orrin", 0), ("e5f6a7b8", "Vessa", 2), ("c9d0e1f2", "Tamsin", 4))


class Stage:
    def __init__(self) -> None:
        _DATA.mkdir(parents=True)
        self.root = root = tk.Tk()
        host = self.host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host.config = {}
        host._config_path = _DATA / "config.json"
        host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        host._session_rooms.open(sr.MAIN, "claude", "moon-forge")
        ensure_topic(_DATA, "moon-forge")
        set_topic(_DATA, "moon-forge", title="Moon forge", project="moon-forge", status="open")
        for aid, _name, _start in AGENTS:
            join_topic(_DATA, "moon-forge", aid)
        self.agents = {aid: AgentInfo(aid, name, status=CYCLE[start], skin="caine", source="claude",
                                      project="moon-forge", last_seen=time.time()) for aid, name, start in AGENTS}
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
        dungeon_nav.jump(host, "moon-forge")
        self.tick(1.0)
        boss = boss_view.view_for(self.book)
        if boss.chart_shown():  # the Friday burn-down covers the room
            boss.toggle_chart()
        self.tick(0.5)

    def set(self, aid: str, status: str) -> None:
        self.agents[aid].status = status
        self.host._inside[aid].agent = self.agents[aid]

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

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def crop(self) -> tuple[int, int, int, int]:
        """The avatars and their plates, with a margin, in window pixels."""
        scene, marks = self.scene, status_ink.marks(self.scene)
        boxes = [scene.bbox(av.spr_id) for av in self.host._inside.values() if av.spr_id]
        boxes += [scene.bbox(marks.item(aid)) for aid in self.agents if marks.item(aid)]
        boxes = [b for b in boxes if b]
        ox = scene.winfo_rootx() - self.root.winfo_rootx()
        oy = scene.winfo_rooty() - self.root.winfo_rooty()
        left, top = min(b[0] for b in boxes) - 170, min(b[1] for b in boxes) - 60
        right, bottom = max(b[2] for b in boxes) + 170, max(b[3] for b in boxes) + 90
        return (max(0, left + ox), max(0, top + oy), min(W, right + ox), min(H, bottom + oy))


def legend(width: int, active: str) -> Image.Image:
    """A strip naming each state in its colour; the one that just changed is boxed."""
    strip = Image.new("RGB", (width, 44), (23, 16, 34))
    draw = ImageDraw.Draw(strip)
    font = ImageFont.load_default(size=19)
    words = [(s, status_ink.word(s)) for s in CYCLE]
    gap = 22
    total = sum(int(draw.textlength(w, font=font)) for _, w in words) + gap * (len(words) - 1)
    x = (width - total) // 2
    for state, word in words:
        w = int(draw.textlength(word, font=font))
        if state == active:
            draw.rounded_rectangle((x - 7, 7, x + w + 7, 37), radius=6, outline=status_ink.colour(state), width=2)
        draw.text((x, 11), word, fill=status_ink.colour(state), font=font)
        x += w + gap
    draw.line((0, 43, width, 43), fill=(224, 170, 62), width=2)
    return strip


def film(stage: Stage, out: Path) -> None:
    box = stage.crop()
    frames = []
    index = {aid: start for aid, _name, start in AGENTS}
    active = ""

    def shoot(seconds: float) -> None:
        for _ in range(max(1, round(seconds / STEP))):
            stage.tick(STEP)
            shot = stage.grab().crop(box)
            shot = shot.resize((shot.width * 2, shot.height * 2), Image.NEAREST)
            frame = Image.new("RGB", (shot.width, shot.height + 44))
            frame.paste(legend(shot.width, active), (0, 0))
            frame.paste(shot, (0, 44))
            frames.append(frame.quantize(colors=128, method=Image.Quantize.FASTOCTREE))

    shoot(1.0)
    for turn in range(len(CYCLE) + 2):
        aid = AGENTS[turn % len(AGENTS)][0]
        index[aid] = (index[aid] + 1) % len(CYCLE)
        active = CYCLE[index[aid]]
        stage.set(aid, active)
        shoot(1.1)
    frames[0].save(out / "status-colors.gif", save_all=True, append_images=frames[1:], duration=int(STEP * 1000),
                   loop=0, optimize=True)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    cues.play = lambda _app, _name: None
    inside_roster.Hall.paint_user = lambda _hall, _scene, _photos, _now: None  # the keeper would hide a plate
    load_sprites(REGISTRY)
    stage = Stage()
    film(stage, out)
    stage.tick(0.8)
    stage.grab().save(out / "status-1366.png")
    stage.root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
