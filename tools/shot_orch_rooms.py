"""ORCH.ROOM evidence: two orchestrators meet, the Topics rows and door signs, a proposed card.

Made-up rooms, names and cards in a temporary data folder; no real session, chat or board is read.
Draws the real Dungeon floor on a Tk canvas and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_orch_rooms.py <out-dir>
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="orch-rooms-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from cli_avatars.app import inside_roster  # noqa: E402
from cli_avatars.app import orch_rooms as orch  # noqa: E402
from cli_avatars.app import orch_dock  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, join_topic  # noqa: E402

W, H, DOCK = 1180, 760, 360
ORRIN, VESSA, QUILL = "a1b2c3d4", "e5f6a7b8", "c9d0e1f2"
AGENTS = (
    (ORRIN, "Orrin", "release-train", "ember_mage", "busy"),
    (VESSA, "Vessa", "harbor-map", "forest_scout", "thinking"),
    (QUILL, "Quill", "lantern-docs", "frost_wanderer", "busy"),
)
CARDS = (
    ("release-train", "Cut the branch", "todo", ""), ("release-train", "Tag the build", "todo", ""),
    ("release-train", "Mend the gate", "doing", "step 2 of 3: hinges oiled"),
    ("release-train", "Write notes", "review", ""),
    ("harbor-map", "Chart the reef", "doing", "soundings at 40%"),
    ("harbor-map", "Find the key", "blocked", "needs the vault code"),
    ("lantern-docs", "Trim the wicks", "doing", "first draft done"), ("lantern-docs", "Index", "todo", ""),
)


def _seed(model) -> None:
    model.open(sr.MAIN, "claude", "release-train")
    model.open(sr.SIMPLE, "claude", "harbor-map")
    model.open(sr.SIMPLE, "claude", "lantern-docs")
    reg = Registry(_DATA)
    for topic in ("release-train", "harbor-map", "lantern-docs"):
        ensure_topic(_DATA, topic, ts=1)
    for topic, title, column, note in CARDS:
        card = reg.task_create(topic, title, topic=topic)
        if column != "todo":
            reg.task_move(card["id"], column)
        if note:
            reg.change(card["id"], lambda c, n=note: {**c, "status_note": n}, "claude:" + ORRIN)


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [1_795_000_000.0]
        self.talk: list = []
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        _seed(self.model)
        self.agents = {aid: AgentInfo(aid, name, status=state, skin=skin, source="claude", project=project,
                                      last_seen=self.clock[0])
                       for aid, name, project, skin, state in AGENTS}
        self.dock = tk.Frame(root, bg="#0d0d1a", width=DOCK, height=H)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.canvas = tk.Canvas(root, width=W - DOCK, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None,
            _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in self.agents.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: self.agents),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in self.agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: list(self.talk)
        hall._rooms = lambda: ([], [])
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.book.draw_inside()

    def grab(self, box=None) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        shot = ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))
        return shot.crop(box) if box else shot

    def say(self, sender: str, to: str, ago: float = 0.0) -> None:
        self.talk.append(orch.Talk(self.clock[0] - ago, "claude:" + sender, ("claude:" + to,)))


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w = 9 * len(text) + 24
    draw.rectangle((10, 10, 10 + w, 40), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((22, 18), text, fill=(240, 230, 200))
    return out


def meeting(stage: Stage, out: Path) -> None:
    box = (DOCK, 0, W, H)
    frames = []

    def film(seconds: float, text: str, every: float = 0.2) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            frames.append(caption(stage.grab(box), text))

    film(2.0, "Orrin (release-train) and Vessa (harbor-map) at home")
    stage.say(ORRIN, VESSA)
    film(1.0, "Orrin asks Vessa: say --to")
    stage.say(VESSA, ORRIN)
    film(9.0, "Vessa answers within 5 min: Vessa walks to Orrin's room")
    film(3.0, "The meeting: Orrin hosts, Vessa visits")
    stage.clock[0] += orch.QUIET_S
    film(9.0, "3 quiet minutes later: Vessa walks home")
    frames[0].save(out / "meeting.gif", save_all=True, append_images=frames[1:], duration=200, loop=0,
                   optimize=True)


def tracker(stage: Stage, out: Path) -> None:
    stage.tick(1.0)
    rows = orch_dock.rows(stage.app)
    orch_dock.render(stage.app, stage.dock, rows)
    stage.tick(0.5)
    stage.grab().save(out / "tracker.png")


def propose(stage: Stage, out: Path) -> None:
    """The Tasks board of release-train after its orchestrator proposed a card; another topic is refused."""
    from cli_avatars.app.tasks_panel import TasksPanel

    join_topic(_DATA, "release-train", "claude:" + ORRIN)
    api = AgentApi(Registry(_DATA), via="mcp")
    api.task_propose("claude:" + ORRIN, "release-train", "Draft the release notes", "release-train")
    refused = ""
    try:
        api.task_propose("claude:" + ORRIN, "harbor-map", "Not my topic", "harbor-map")
    except Exception as exc:  # noqa: BLE001
        refused = getattr(exc, "reason", str(exc))
    for child in stage.root.winfo_children():
        child.pack_forget()
    host = tk.Frame(stage.root, bg="#0d0d1a", width=W, height=H)
    host.pack(fill="both", expand=True)
    panel = TasksPanel(host, lambda: _DATA, lambda: "release-train")
    panel.refresh(force=True)
    stage.root.update()
    shot = stage.grab()
    text = f"Orrin proposed 'Draft the release notes' (todo, label proposed); on harbor-map: refused, {refused}"
    framed = caption(shot.crop((0, 0, W, H - 50)).crop((0, -50, W, H - 50)), text)
    framed.save(out / "propose.png")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    load_sprites(REGISTRY)
    root = tk.Tk()
    root.geometry(f"{W}x{H}+0+0")
    stage = Stage(root)
    stage.tick(12.0)
    meeting(stage, out)
    tracker(stage, out)
    propose(stage, out)
    root.destroy()
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
