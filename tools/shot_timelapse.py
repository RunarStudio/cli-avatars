"""TIMELAPSE evidence: open the time-lapse, scrub yesterday while avatars walk room to room, tap a moment, the
task chat opens at that message, Esc returns to the live floor.

Made-up rooms, sessions, cards, chat lines and room log in a temporary data folder; no real session, chat or board
is read. It draws the real Dungeon floor and the chat dock on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_timelapse.py <out-dir>

Writes ``time-lapse.gif`` and ``desktop-1366.png``. ``seed`` gives the same data for a phone shot.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DATA = Path(tempfile.mkdtemp(prefix="lapse-shot-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
os.environ["PATH"] = ""  # the chat dock shows "Claude CLI not found", never a binary's path

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

import timelapse  # noqa: E402
from board.store import LocalStore  # noqa: E402
from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, inside_roster, timelapse_view  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import timelapse_art as art  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.render import PhotoCache  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.model.room import add_participant  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from events import StateEvent, append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

W, H, DOCK = 1366, 768, 430
PROJECT = "lantern"
DAY = date.today() - timedelta(days=1)
ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))
AGENTS = (("a1b2c3d4", "Orrin", "moon-forge", "busy"), ("e5f6a7b8", "Vessa", "glass-orchard", "busy"))
CARDS = (("moon-forge", "Polish the moon gate"), ("glass-orchard", "Count the glass apples"),
         ("ember-ledger", "Balance the ledger"))
WALKS = (("daniel", "user", "You", ((7, 40, "Apothecary"),)),
         ("claude:a1b2c3d4", "orchestrator", "Orrin", ((8, 0, "moon-forge"), (13, 20, "glass-orchard"),
                                                     (15, 0, "moon-forge"))),
         ("claude:e5f6a7b8", "orchestrator", "Vessa", ((8, 30, "glass-orchard"), (12, 0, "ember-ledger"),
                                                     (17, 40, "glass-orchard"))))


def epoch(hour: int, minute: int = 0) -> float:
    return datetime.combine(DAY, dtime(hour, minute)).timestamp()


def iso(hour: int, minute: int = 0) -> str:
    return datetime.fromtimestamp(epoch(hour, minute), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed(model) -> dict:
    """Rooms, cards, a task chat, board events, chat lines and the room log of a made-up yesterday."""
    reg = Registry(_DATA)
    cards = {}
    for topic, kind, title in ROOMS:
        model.open(kind, "claude", topic)
        set_topic(_DATA, topic, title=title, project=PROJECT, status="open")
    for topic, title in CARDS:
        cards[title] = reg.task_create(PROJECT, title, topic=topic)["id"]
    apples = cards["Count the glass apples"]
    chat = f"task-{apples[:8]}-1"
    reg.store.update(apples, lambda c: ({**c, "chats": [{"id": str(uuid.uuid4()), "cli": "claude",
                                                       "created": iso(11), "room": chat}]}, []))
    set_topic(_DATA, chat, title="Count the glass apples · chat 1", project=PROJECT, status="open")
    add_participant(_DATA, chat, "claude")
    store = LocalStore(_DATA)
    events = ((9, 10, cards["Polish the moon gate"], "moved", {"from": "todo", "to": "doing"}),
              (11, 30, apples, "commented", {"text": "Ripe ones first"}),
              (14, 10, cards["Balance the ledger"], "moved", {"from": "todo", "to": "doing"}),
              (16, 20, cards["Polish the moon gate"], "decision", {"text": "answered: Silver polish"}))
    for hour, minute, card, kind, extra in events:
        store.append_event({"id": str(uuid.uuid4()), "ts": iso(hour, minute), "card": card, "actor": "daniel",
                            "kind": kind, **extra})
    for hour, minute in ((11, 32), (18, 5)):
        store.append_event({"id": str(uuid.uuid4()), "ts": iso(hour, minute), "card": None, "actor": "daniel",
                            "kind": "prompt", "room": chat, "target": "claude", "outcome": "ok"}, project=PROJECT)
    lines = ((11, 32, "user", chat, "Count only the ripe ones."), (11, 34, "claude:room", chat,
                                                                   "Forty-two ripe, nine still green."),
             (14, 30, "grok:north001", "ember-ledger", "Ledger balanced to the last copper."),
             (18, 5, "user", chat, "Box the ripe ones for the fair."),
             (18, 7, "claude:room", chat, "Boxed: six crates, straw between each row."))
    for hour, minute, sender, room, note in lines:
        append_channel(_DATA, {"ts": epoch(hour, minute), "from": sender, "to": "user" if sender != "user" else
                               "claude:room", "channel": room, "icon": "speech", "note": note, "kind": "msg"})
    log = timelapse.Log(lambda: _DATA)
    for aid, kind, name, stops in WALKS:
        for hour, minute, room in stops:
            log.rooms([{"id": aid, "kind": kind, "name": name, "room": room}], epoch(hour, minute))
    log.on_event(StateEvent("claude", "a1b2c3d4ffff", "busy", epoch(9, 0), "udp",
                            task=cards["Polish the moon gate"][:8]))
    log.on_event(StateEvent("claude", "e5f6a7b8ffff", "blocked", epoch(12, 40), "udp"))
    return {"cards": cards, "chat": chat}


class Stage:
    def __init__(self, root) -> None:
        self.root = root
        self.clock = [time.time()]
        self.model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        self.seeded = seed(self.model)
        agents = {aid: AgentInfo(aid, name, status=state, skin="caine", source="claude", project=project,
                                 last_seen=self.clock[0]) for aid, name, project, state in AGENTS}
        self.canvas = tk.Canvas(root, width=W - DOCK, height=H, bg="#06040b", highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.dock = tk.Frame(root, bg="#0d0d1a", width=DOCK, height=H)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.canvas._rooms_painter = RoomsPainter(source=lambda: self.model.layout(self.clock[0]))
        self.chat = ChatWindow(root, directory=_DATA, agents=[], config={}, container=self.dock, room_pane=RoomPane)
        self.app = SimpleNamespace(
            root=root, config={}, desktop_escape=False, _drag_av=None, render=SimpleNamespace(photos=PhotoCache()),
            places=None, _inside={aid: Avatar(a, 800, 600, 0, REGISTRY, spring_mode=True) for aid, a in agents.items()},
            _chat_directory=lambda: _DATA, scanner=SimpleNamespace(get_agents=lambda: agents),
            dungeon=SimpleNamespace(scene=self.canvas, _zoom=1, _pan=(0, 0), _offscreen=True),
            _select_topic=lambda topic: None, _session_rooms=self.model, _chat_window=self.chat,
            _show_chat=lambda topic_id=None, address_id=None: self.chat.open(topic_id=topic_id))
        self.book = PlaceBook(self.app, path=None)
        self.app.places = self.book
        for aid in agents:
            self.book._actors[aid] = Place(aid, INSIDE, "new", None)
        hall = inside_roster.hall(self.book)
        hall._talk = lambda: []
        hall._rooms = lambda: ([], [])
        root.update()
        self.canvas._rooms_painter.paint(self.canvas)
        self.lapse = timelapse_view.lapse_for(self.book)
        self.tick(0.2)

    def tick(self, seconds: float, step: float = 0.05) -> None:
        for _ in range(max(1, round(seconds / step))):
            self.clock[0] += step
            self.book._now = self.clock[0]
            self.lapse._clock = time.monotonic() - step
            self.book.draw_inside()
            timelapse_view.paint(self.book)

    def grab(self) -> Image.Image:
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def bar_point(self, minute: float, by: float) -> tuple[float, float]:
        x0, y0, width = self.lapse._bar
        return x0 + art.track_x(minute, width) * timelapse_view.K, y0 + by * timelapse_view.K


def caption(image: Image.Image, text: str) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w = 7 * len(text) + 24
    draw.rectangle((10, 10, 10 + w, 36), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((22, 17), text, fill=(240, 230, 200))
    return out


def film(stage: Stage, out: Path) -> None:
    frames = []

    def shoot(seconds: float, text, every: float = 0.25) -> None:
        for _ in range(round(seconds / every)):
            stage.tick(every)
            words = text() if callable(text) else text
            frames.append(caption(stage.grab(), words).convert("P", palette=Image.ADAPTIVE, colors=128))

    shoot(1.0, "Live Dungeon floor; the TIME-LAPSE plate sits bottom left")
    box = stage.canvas.bbox(stage.lapse._items["entry"])
    stage.lapse.press((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    stage.lapse.go(-1)
    stage.lapse.seek(7 * 60 + 30, tick=False)
    shoot(1.0, "TIME-LAPSE: the live floor goes under the map tinted to the hour; < > walk the last 30 days")
    stage.lapse.speed = 2
    stage.lapse.toggle_play()
    shoot(10.4, lambda: f"Play x16 · {timelapse.clock(stage.lapse.minute)} · avatars walk room to room, trails fade")
    stage.lapse.toggle_play()
    stage.lapse.seek(13 * 60 + 17, tick=False)
    stage.tick(0.25)
    stage.grab().save(out / "desktop-1366.png")
    shoot(1.5, "Scrub back to 13:17: Orrin walks through the doors to the Glass orchard")
    stage.lapse.press(*stage.bar_point(18 * 60 + 7, 12))
    shoot(2.5, "Tap the 18:07 gem: the task chat opens at that message, lit (moment cue)")
    stage.lapse.leave()
    shoot(1.0, "Esc or LEAVE: back to the live floor")
    frames[0].save(out / "time-lapse.gif", save_all=True, append_images=frames[1:], duration=160, loop=0,
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
