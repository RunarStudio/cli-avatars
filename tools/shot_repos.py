"""REPOS.1 evidence: the Repos tab beside the Dungeon floor, under Xvfb.

Made-up rooms, sessions and repo folders in a temporary data folder; working folders come from a fixture table,
not from real sessions. No CLI starts and no git runs.

    xvfb-run -a python tools/shot_repos.py <out-dir>

Writes ``repos.gif`` (add a repo, Caine starts in it with a subagent, the seal lights, the room badge shows) and
``desktop-1366.png``.
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

_TMP = Path(tempfile.mkdtemp(prefix="repos-shot-"))
_DATA = _TMP / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

import sessions  # noqa: E402
from cli_avatars.app import cues, inside_roster, repos_live, repos_panel  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_panes import install_fonts  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from topics import set_topic  # noqa: E402

W, H, DOCK = 1366, 768, 560
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "ember_mage", "busy", None),
          ("a1b2c3d5", "Wren", "moon-forge", "forest_scout", "thinking", "a1b2c3d4"),
          ("e5f6a7b8", "Vessa", "glass-orchard", "frost_wanderer", "busy", None))


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        _DATA.mkdir(parents=True)
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        for topic, kind, title in ROOMS:
            self.model.open(kind, "claude", topic)
            set_topic(_DATA, topic, title=title, project="lantern", status="open")
        self.agents = {aid: AgentInfo(aid, name, status=state, skin=skin, source="claude", project=project,
                                      parent_id=parent, last_seen=self.clock[0])
                       for aid, name, project, skin, state, parent in AGENTS}
        self.cwds = {"a1b2c3d4": "/w/moon-forge", "e5f6a7b8": "/w/glass-orchard"}
        sessions.agent_cwd = lambda aid: self.cwds.get(aid, "")
        self.dock = tk.Frame(root, bg="#141018", width=DOCK, height=H)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.canvas = tk.Canvas(root, width=W - DOCK, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        tops = {aid: a for aid, a in self.agents.items() if not a.parent_id}
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in tops.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: dict(self.agents)),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True, _center="repos"),
            _select_topic=lambda topic: None, _session_rooms=self.model)
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in tops:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: []
        hall._rooms = lambda: ([], [])
        self.panel = repos_panel.ensure(SimpleNamespace(app=self.app, _repos=self.dock))
        repos_live.tick(self.app, self.clock[0], force=True)
        self.panel.refresh(force=True)
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.tick(0.2)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.book.draw_inside()
        self.panel.refresh()

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w = 7 * len(text) + 24
    x = DOCK + 10
    draw.rectangle((x, H - 40, x + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((x + 12, H - 33), text, fill=(240, 230, 200))
    return out


def film(stage: Stage, frames: list, seconds: float, text: str, every: float = 0.2) -> None:
    for _ in range(round(seconds / every)):
        stage.tick(every)
        frames.append(caption(stage.grab(), text).resize((W * 3 // 4, H * 3 // 4), Image.LANCZOS))


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    played = []
    cues.play = lambda _app, name: played.append(name)
    load_sprites(REGISTRY)
    root = tk.Tk()
    root.geometry(f"{W}x{H}+0+0")
    install_fonts(root)
    stage = Stage(root)
    stage.tick(3.0)
    frames: list[Image.Image] = []
    film(stage, frames, 1.6, "Repos tab: no repos yet")
    folder = _TMP / "w" / "lantern-forge"
    (folder / "src").mkdir(parents=True)
    for n in range(1, len("Lantern Forge") + 1, 3):
        stage.panel.name.delete(0, "end")
        stage.panel.name.insert(0, "Lantern Forge"[:n])
        film(stage, frames, 0.2, "Add a repo: a name and its folder (typed, or Browse)")
    stage.panel.name.delete(0, "end")
    stage.panel.name.insert(0, "Lantern Forge")
    film(stage, frames, 0.6, "Add a repo: a name and its folder (typed, or Browse)")
    stage.panel.path.insert(0, str(folder))
    stage.panel.add_button.invoke()
    film(stage, frames, 2.0, "Added: the row shows the folder name; the seal is dark, nobody works in it")
    stage.cwds["a1b2c3d4"] = str(folder / "src")
    stage.app._repo_live.at = float("-inf")
    film(stage, frames, 3.0, "Orrin (Caine, the throne room) starts in it with a subagent: the seal lights")
    film(stage, frames, 3.0, "Moon forge carries the repo's badge on the map; a soft rune cue")
    frames[0].save(out / "repos.gif", save_all=True, append_images=frames[1:], duration=200, loop=0, optimize=True)
    stage.tick(0.2)
    stage.grab().resize((W, H)).save(out / "desktop-1366.png")
    root.destroy()
    print("cues", played)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
