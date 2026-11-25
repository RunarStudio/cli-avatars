"""NAV.1 and LAYOUT.1 evidence: the real Dungeon window under Xvfb, driven by generated Tk events.

Made-up rooms, orchestrators and a decision in a temporary data folder. No CLI starts, no git runs, no network.

    xvfb-run -a -s "-screen 0 1600x900x24" python tools/shot_nav.py <out-dir>

Writes ``navigate.gif`` (wheel zoom, drag, WASD, a Topics row glide with its light, the mini-map, Home),
``desktop-1366.png`` (zoomed in), ``resize.gif`` (both splitters dragged, a column collapsed and reset, the
window narrowed and widened) and ``desktop-900.png`` (a narrow window).
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

_TMP = Path(tempfile.mkdtemp(prefix="nav-shot-"))
_DATA = _TMP / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from bots.service import BotService  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import cues, dungeon_nav, dungeon_sash, inside_roster  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
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
from topics import ensure_topic, set_topic  # noqa: E402

W, H = 1366, 768
STEP = 0.1
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("salt-archive", sr.SIMPLE, "Salt archive"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "ember_mage", "busy"),
          ("e5f6a7b8", "Vessa", "glass-orchard", "frost_wanderer", "thinking"),
          ("c9d0e1f2", "Tamsin", "salt-archive", "forest_scout", "busy"))


class Stage:
    def __init__(self) -> None:
        _DATA.mkdir(parents=True)
        self.root = root = tk.Tk()
        self.clock = time.time()
        self.cursor = None
        host = self.host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host.config = {}
        host._config_path = _DATA / "config.json"
        self.model = host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        for topic, kind, title in ROOMS:
            self.model.open(kind, "claude", topic)
            ensure_topic(_DATA, topic)
            set_topic(_DATA, topic, title=title, project="lantern", status="open")
        ask_decision(_DATA, agent="claude:a1b2c3d4", room="moon-forge", question="Cast the bell in bronze?",
                     options=["a=yes", "b=iron"])
        self.agents = {aid: AgentInfo(aid, name, status=state, skin=skin, source="claude", project=project,
                                      last_seen=self.clock) for aid, name, project, skin, state in AGENTS}
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
        self.size(W, H)
        host._build_rooms_win()
        host._update_rooms_win(True)
        view.set_right(True, "needs")
        self.book = host.places = PlaceBook(host, path=None)
        self.book.attach()
        for aid in self.agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: []
        hall._rooms = lambda: ([], [])
        self.scene = view.scene
        self.tick(1.0)

    def size(self, w: int, h: int) -> None:
        self.root.geometry(f"{w}x{h}+0+0")
        for _ in range(3):
            self.root.update()

    def tick(self, seconds: float) -> None:
        end = time.time() + seconds
        while True:
            self.clock = time.time()
            self.book._now = self.clock
            self.book.draw_inside()
            dungeon_nav.paint(self.book)
            self.root.update()
            if self.clock >= end:
                return
            time.sleep(max(0.0, min(0.04, end - time.time())))

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY"))

    def at(self, x: float, y: float) -> tuple[int, int]:
        """Root-relative point of a scene point, for the drawn cursor."""
        return (self.scene.winfo_rootx() - self.root.winfo_rootx() + int(x),
                self.scene.winfo_rooty() - self.root.winfo_rooty() + int(y))

    def mouse(self, sequence: str, x: float, y: float, **kw) -> None:
        self.cursor = self.at(x, y)
        self.scene.event_generate(sequence, x=int(x), y=int(y), **kw)

    def key(self, keysym: str) -> None:
        self.scene.focus_force()
        self.scene.event_generate("<KeyPress>", keysym=keysym)

    def room_point(self, room: str) -> tuple[float, float]:
        painter = self.scene._rooms_painter
        return painter.to_canvas(*Plan.from_layout(painter.layout).floor(room).centre())


class Film:
    def __init__(self, stage: Stage, scale: float) -> None:
        self.stage, self.scale, self.frames = stage, scale, []

    def shoot(self, seconds: float, text: str) -> None:
        for _ in range(max(1, round(seconds / STEP))):
            self.stage.tick(STEP)
            self.frames.append(self.frame(text))

    def frame(self, text: str) -> Image.Image:
        shot = self.stage.grab()
        canvas = Image.new("RGB", (W, H + 34), (12, 10, 16))
        canvas.paste(shot.crop((0, 0, min(W, shot.width), min(H, shot.height))), (0, 34))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, W, 33), fill=(23, 16, 34))
        draw.line((0, 33, W, 33), fill=(224, 170, 62), width=2)
        draw.text((14, 11), text, fill=(240, 230, 200))
        if self.stage.cursor is not None:
            x, y = self.stage.cursor
            arrow = [(x, y + 34), (x, y + 52), (x + 5, y + 47), (x + 9, y + 56), (x + 12, y + 54), (x + 8, y + 46),
                     (x + 14, y + 46)]
            draw.polygon(arrow, fill=(250, 246, 232), outline=(10, 8, 14))
        small = canvas.resize((int(W * self.scale), int((H + 34) * self.scale)), Image.LANCZOS)
        return small.quantize(colors=128, method=Image.Quantize.FASTOCTREE)

    def save(self, path: Path) -> None:
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:], duration=int(STEP * 1000), loop=0,
                            optimize=True)


def navigate(stage: Stage, out: Path) -> None:
    film = Film(stage, 0.6)
    scene = stage.scene
    w, h = scene.winfo_width(), scene.winfo_height()
    film.shoot(1.2, "The whole Dungeon map: three session rooms around the Apothecary")
    x, y = stage.room_point("moon-forge")
    for _ in range(2):
        stage.mouse("<Button-4>", x + 30, y)
        film.shoot(0.6, "Mouse wheel: zoom in, one whole step at a time, anchored at the cursor (1x-3x)")
    px, py = w * 0.62, h * 0.30
    stage.mouse("<ButtonPress-1>", px, py)
    for n in range(1, 16):
        stage.mouse("<Motion>", px - 14 * n, py + 9 * n, state=0x100)
        film.shoot(STEP, "Drag on empty floor: the map follows the hand")
    stage.mouse("<ButtonRelease-1>", px - 210, py + 135)
    film.shoot(0.4, "Drag on empty floor: the map follows the hand")
    for keysym in ("d", "d", "d", "d", "s", "s", "s", "a", "w"):
        stage.key(keysym)
        film.shoot(0.2, f"WASD and arrow keys pan: {keysym.upper()}")
    stage.cursor = None
    row = _topics_row(stage, "salt-archive")
    if row is not None:
        stage.cursor = (row.winfo_rootx() - stage.root.winfo_rootx() + 60,
                        row.winfo_rooty() - stage.root.winfo_rooty() + 14)
        row.event_generate("<Button-1>", x=60, y=14)
    film.shoot(2.4, "Topics row click: the camera glides to Salt archive and its light rises")
    nav = dungeon_nav.widget_for(stage.view)
    tx, ty, tw, th, _k = nav.thumb
    stage.mouse("<ButtonPress-1>", tx + tw * 0.25, ty + th * 0.55)
    stage.mouse("<ButtonRelease-1>", tx + tw * 0.25, ty + th * 0.55)
    film.shoot(1.4, "Mini-map: click a spot and the view box glides there")
    l, t, r, b = nav.rects["plus"]
    stage.mouse("<ButtonPress-1>", (l + r) / 2, (t + b) / 2)
    stage.mouse("<ButtonRelease-1>", (l + r) / 2, (t + b) / 2)
    film.shoot(0.8, "Map control: + zooms in, - zooms out, the corners button shows the whole map")
    stage.key("Home")
    film.shoot(1.6, "Home: back to the whole map")
    x, y = stage.room_point("glass-orchard")
    stage.cursor = stage.at(x + 36, y + 14)
    stage.host._on_scene_double(SimpleNamespace(x=x + 36, y=y + 14, x_root=0, y_root=0))
    film.shoot(2.0, "Double-click a room: glide there and light it")
    stage.cursor = None
    film.save(out / "navigate.gif")
    stage.tick(1.2)
    stage.grab().save(out / "desktop-1366.png")


def resize(stage: Stage, out: Path) -> None:
    film = Film(stage, 0.6)
    stage.key("Home")
    stage.tick(0.6)
    view = stage.view
    body = view._mid.master

    def drag(frame, low, high, xs, text):
        for x in xs:
            view.drag_dock(frame, SimpleNamespace(x_root=body.winfo_rootx() + x, y_root=0, x=0, y=0), low, high)
            sash = view._sash_l if frame is view._left else view._sash_r
            stage.cursor = (sash.winfo_rootx() - stage.root.winfo_rootx() + 3, 300)
            film.shoot(STEP, text)

    film.shoot(0.8, "Splitters between the map and each column (ember grip)")
    drag(view._left, 160, 640, range(282, 480, 18), "Drag the Topics splitter wider")
    drag(view._left, 160, 640, range(480, 170, -24), "... and narrower (160 px minimum)")
    right = body.winfo_width()
    drag(view._right, 200, 720, range(right - 362, right - 640, -24), "Drag the Chat / Needs you splitter wider")
    drag(view._right, 200, 720, range(right - 640, right - 230, 30), "... and narrower")
    drag(view._right, 200, 720, (right - 120, right - 60), "Under half the minimum it collapses to a thin edge")
    film.shoot(0.8, "Under half the minimum it collapses to a thin edge")
    dungeon_sash.reset(view, "right")
    dungeon_sash.reset(view, "left")
    film.shoot(1.0, "Double-click a splitter: back to the default width")
    stage.cursor = None
    for width in (1300, 1180, 1060, 960, 900, 820, 760):
        stage.size(width, H)
        film.shoot(0.3, f"Window {width} px: the columns shrink, the map keeps room and refits")
    stage.size(900, 700)
    stage.tick(0.4)
    stage.grab().save(out / "desktop-900.png")
    for width in (820, 960, 1100, 1240, 1366):
        stage.size(width, H)
        film.shoot(0.3, f"Window {width} px: the picked widths come back")
    film.shoot(0.8, "Nothing stuck")
    film.save(out / "resize.gif")


def _topics_row(stage: Stage, topic: str):
    todo = [stage.host._rooms_list] if getattr(stage.host, "_rooms_list", None) is not None else []
    while todo:
        widget = todo.pop()
        if isinstance(widget, tk.Label) and f" {topic} " in widget.cget("text"):
            return widget
        todo.extend(widget.winfo_children())
    return None


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    played = []
    cues.play = lambda _app, name: played.append(name)
    load_sprites(REGISTRY)
    stage = Stage()
    navigate(stage, out)
    resize(stage, out)
    print("cues:", ", ".join(played) or "none")
    stage.root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
