"""YOU-AVATAR evidence: the real Dungeon window under Xvfb, driven by generated Tk events, on made-up data.

Orrin works in the Moon forge (the throne room), Vessa in the Glass orchard. Your keeper starts on the throne
room's floor, walks by a click and by held keys through a door, and then Vessa is asked a decision: a ``?`` bubble
over her, the badge over you, and walking up to her opens her chat. No CLI starts, no git runs, no network.

    xvfb-run -a -s "-screen 0 1600x900x24" python tools/shot_you.py <out-dir>

Writes ``you-avatar.gif``, ``needs-you.gif`` and ``desktop-1366.png``.
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

_TMP = Path(tempfile.mkdtemp(prefix="you-shot-"))
_DATA = _TMP / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from bots.service import BotService  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import cues, decide_watch, dungeon_nav, inside_roster, needs_panel, you_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.app.shell import OverlayApp  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from decisions import ask_decision  # noqa: E402
from routing import PointerGesture  # noqa: E402
from topics import ensure_topic, join_topic, set_topic  # noqa: E402

W, H = 1366, 768
STEP = 0.1
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "busy"), ("e5f6a7b8", "Vessa", "glass-orchard", "thinking"))


class Stage:
    def __init__(self) -> None:
        _DATA.mkdir(parents=True)
        self.root = root = tk.Tk()
        self.cursor = None
        host = self.host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host.config = {}
        host._config_path = _DATA / "config.json"
        self.model = host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        for topic, kind, title in ROOMS:
            self.model.open(kind, "claude", topic)
            ensure_topic(_DATA, topic)
            set_topic(_DATA, topic, title=title, project=topic, status="open")
        for aid, _name, topic, _state in AGENTS:
            join_topic(_DATA, topic, aid)
        self.agents = {aid: AgentInfo(aid, name, status=state, skin="caine", source="claude", project=project,
                                      last_seen=time.time()) for aid, name, project, state in AGENTS}
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
        host._inside = {aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in self.agents.items()}
        view = self.view = host.dungeon = DungeonWindow(host)
        view.build(offscreen=True)
        root.deiconify()
        root.geometry(f"{W}x{H}+0+0")
        for _ in range(3):
            root.update()
        host._build_rooms_win()
        host._update_rooms_win(True)
        view.set_right(True, "needs")
        self.book = host.places = PlaceBook(host, path=None)
        self.book.attach()
        for aid in self.agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        inside_roster.hall(self.book)._talk = lambda: []
        self.scene = view.scene
        self.tick(1.0)

    def tick(self, seconds: float) -> None:
        end = time.time() + seconds
        while True:
            now = time.time()
            self.book._now = now
            for agent in self.agents.values():
                agent.last_seen = now
            needs_panel.step(self.host)
            decide_watch.step(self.host)
            self.book.draw_inside()
            dungeon_nav.paint(self.book)
            self.root.update()
            if now >= end:
                return
            time.sleep(max(0.0, min(0.04, end - time.time())))

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def at(self, x: float, y: float) -> tuple[int, int]:
        return (self.scene.winfo_rootx() - self.root.winfo_rootx() + int(x),
                self.scene.winfo_rooty() - self.root.winfo_rooty() + int(y))

    def click(self, x: float, y: float) -> None:
        self.cursor = self.at(x, y)
        self.scene.event_generate("<ButtonPress-1>", x=int(x), y=int(y))
        self.scene.event_generate("<ButtonRelease-1>", x=int(x), y=int(y))

    def key(self, keysym: str, up: bool = False) -> None:
        self.scene.focus_force()
        self.scene.event_generate("<KeyRelease>" if up else "<KeyPress>", keysym=keysym)

    def plan(self) -> Plan:
        return Plan.from_layout(self.scene._rooms_painter.layout)

    def point(self, tile) -> tuple[float, float]:
        return self.scene._rooms_painter.to_canvas(*tile)

    def you(self) -> tuple[float, float]:
        return inside_roster.hall(self.book)._feet[USER_ID]


class Film:
    def __init__(self, stage: Stage, scale: float) -> None:
        self.stage, self.scale, self.frames = stage, scale, []
        self.keys = ""

    def shoot(self, seconds: float, text: str) -> None:
        for _ in range(max(1, round(seconds / STEP))):
            self.stage.tick(STEP)
            self.frames.append(self.frame(text))

    def frame(self, text: str) -> Image.Image:
        shot = self.stage.grab()
        canvas = Image.new("RGB", (W, H + 40), (12, 10, 16))
        canvas.paste(shot, (0, 40))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, W, 39), fill=(23, 16, 34))
        draw.line((0, 39, W, 39), fill=(224, 170, 62), width=2)
        from PIL import ImageFont

        font = ImageFont.load_default(size=20)
        draw.text((16, 9), text, fill=(240, 230, 200), font=font)
        if self.keys:
            w = int(draw.textlength(self.keys, font=font)) + 24
            draw.rounded_rectangle((W - w - 16, 5, W - 16, 34), radius=6, fill=(60, 44, 20), outline=(224, 170, 62))
            draw.text((W - w - 4, 9), self.keys, fill=(255, 230, 160), font=font)
        if self.stage.cursor is not None:
            x, y = self.stage.cursor
            y += 40
            arrow = [(x, y), (x, y + 22), (x + 6, y + 16), (x + 11, y + 27), (x + 15, y + 25), (x + 10, y + 15),
                     (x + 17, y + 15)]
            draw.polygon(arrow, fill=(250, 246, 232), outline=(10, 8, 14))
        small = canvas.resize((int(W * self.scale), int((H + 40) * self.scale)), Image.LANCZOS)
        return small.quantize(colors=160, method=Image.Quantize.FASTOCTREE)

    def save(self, path: Path) -> None:
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:], duration=int(STEP * 1000), loop=0,
                            optimize=True)


def walk_film(stage: Stage, out: Path) -> None:
    film = Film(stage, 0.7)
    dungeon_nav.jump(stage.host, "moon-forge")
    film.shoot(1.6, "Your keeper: crown and lantern, on the throne room floor")
    orchard = stage.plan().floor("glass-orchard")
    stage.click(*stage.point((orchard.centre()[0], orchard.centre()[1] + 1.0)))
    film.shoot(1.0, "Click the floor: it walks there, through the doors")
    view = you_view.view_for(stage.book)
    for _ in range(140):
        film.shoot(STEP, "The camera follows it while it walks")
        if USER_ID not in inside_roster.hall(stage.book)._trips:
            break
    film.shoot(0.6, "The camera follows it while it walks")
    box = view._box
    stage.click((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    film.shoot(1.2, "Click your keeper: the gold ring says it is selected")
    door = next(d for d in stage.plan().doors if "glass-orchard" in (d.a, d.b))
    inner = door.path[0] if door.a == "glass-orchard" else door.path[-1]
    stage.click(*stage.point(inner))
    for _ in range(60):
        film.shoot(STEP, "Walk up to the door")
        if USER_ID not in inside_roster.hall(stage.book)._trips:
            break
    stage.cursor = None
    outer = door.path[-1] if door.a == "glass-orchard" else door.path[0]
    du, dv = outer[0] - inner[0], outer[1] - inner[1]
    combo = {(0, -1): ("Up", "Right"), (0, 1): ("Down", "Left"), (-1, 0): ("Up", "Left"), (1, 0): ("Down", "Right")}
    keys = combo[(0 if abs(du) < 0.5 else (1 if du > 0 else -1), 0 if abs(dv) < 0.5 else (1 if dv > 0 else -1))]
    film.keys = " + ".join(keys) + " held"
    for _ in range(26):
        for k in keys:
            stage.key(k)
        film.shoot(STEP, "Arrow keys or WASD walk it: through the door and down the corridor")
    for k in keys:
        stage.key(k, up=True)
    film.keys = "Esc"
    stage.key("Escape")
    film.shoot(1.0, "Esc lets go of it")
    film.keys = "Left"
    for _ in range(4):
        stage.key("Left")
        film.shoot(0.3, "Not selected: the arrow keys pan the camera again")
    film.keys = ""
    film.save(out / "you-avatar.gif")


def needs_film(stage: Stage, out: Path) -> None:
    film = Film(stage, 0.7)
    dungeon_nav.jump(stage.host, "glass-orchard")
    film.shoot(1.6, "Vessa works in the Glass orchard; nothing waits on you")
    ask_decision(_DATA, agent="claude:e5f6a7b8", room="glass-orchard", question="Copper or silver trim on the gate?",
                 options=["a=Copper", "b=Silver"])
    film.shoot(3.6, "Vessa asks you a decision: a ? bubble over her, a badge over you, Needs you (1)")
    hall = inside_roster.hall(stage.book)
    chat = stage.view._right_tab
    for _ in range(3):
        feet = hall._feet["e5f6a7b8"]
        stage.click(*stage.point((feet[0] + 0.5, feet[1] + 0.5)))
        for _ in range(160):
            film.shoot(STEP, "Walk up to her ...")
            if USER_ID not in hall._trips or stage.view._right_tab != chat:
                break
        if stage.view._right_tab != chat:
            break
    stage.cursor = None
    film.shoot(2.6, "... and her row opens: the chat with the question, as the Needs you tab opens it")
    film.save(out / "needs-you.gif")
    stage.grab().save(out / "desktop-1366.png")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    played = []
    cues.play = lambda _app, name: played.append(name)
    load_sprites(REGISTRY)
    stage = Stage()
    walk_film(stage, out)
    needs_film(stage, out)
    print("cues:", ", ".join(played) or "none")
    stage.root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
