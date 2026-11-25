"""STANDUP evidence: the horn, the agents gather in the throne room, one bubble each (one stuck), the line on a card.

Made-up agents, topics and cards in a temporary data folder; no real session, chat or board is read. It draws the
real Dungeon window (Throne tab, then the Tasks tab with the card open) and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_standup.py <out-dir>

Writes ``standup.gif`` and ``desktop-1366.png``. ``seed`` gives the same data for a phone shot.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

W, H = 1366, 768
STEP_S = 0.2
LORD = ("0a0b0c0d", "Orrin", "ember_mage")
AGENTS = (("a1b2c3d4", "Ash", "forest_scout"), ("b2c3d4e5", "Birch", "frost_wanderer"),
          ("c3d4e5f6", "Cedar", "ponmi"), ("d4e5f6a7", "Dune", "meowatar"))
CARDS = (
    ("a1b2c3d4", "moon-forge", "Polish the moon gate", "doing",
     {"summary": "done: hinges oiled and hung\nnow: the gate frame\nnext: paint the gate silver"}),
    ("b2c3d4e5", "glass-orchard", "Prune the apple rows", "blocked", {"status_note": "waiting on the new shears"}),
    ("c3d4e5f6", "glass-orchard", "Count the glass apples", "doing",
     {"summary": "done: north rows counted\nnow: south rows\nnext: tally the cracked ones"}),
    ("d4e5f6a7", "ember-ledger", "Balance the ember ledger", "review",
     {"summary": "done: weekly sums checked\nnow: review\nnext: close the month"}),
)
TOPICS = (("moon-forge", "Moon forge"), ("glass-orchard", "Glass orchard"), ("ember-ledger", "Ember ledger"))
PROJECT = "lantern"


def seed(data: Path) -> None:
    from registry.facade import Registry
    from topics import set_topic

    for topic, title in TOPICS:
        set_topic(data, topic, title=title, project=PROJECT, status="open")
    reg = Registry(data)
    for who, topic, title, column, extra in CARDS:
        card = reg.task_create(PROJECT, title, topic=topic)
        if extra.get("summary"):
            extra = {**extra, "summary_at": "2026-11-25T08:10:00Z"}
        reg.store.put({**reg.store.get(card["id"]), "assignee": f"claude:{who}", "column": column, **extra},
                      actor=f"claude:{who}")


def agents() -> dict:
    from cli_avatars.model.agent import AgentInfo

    rows = (LORD,) + AGENTS
    return {aid: AgentInfo(agent_id=aid, name=name, parent_id=None, skin=skin, status="busy" if aid != LORD[0]
                           else "thinking", project=PROJECT, is_demo=True, source="claude")
            for aid, name, skin in rows}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="standup-shot-"))
    os.environ["CLI_AVATARS_DATA_DIR"] = str(data)
    try:
        film(data, out)
    finally:
        shutil.rmtree(data, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir()) if p.is_file()))


def film(data: Path, out: Path) -> None:
    import tkinter as tk
    from types import SimpleNamespace

    from PIL import ImageDraw, ImageFont, ImageGrab

    import standup
    from cli_avatars.app import cues, standup_panel
    from cli_avatars.app import standup_show as ss
    from cli_avatars.app.dungeon_window import DungeonWindow
    from cli_avatars.sprites.registry import REGISTRY, load_sprites

    seed(data)
    load_sprites(REGISTRY)
    clock = [100.0]
    standup_panel.CLOCK = lambda: clock[0]
    standup_panel.NOW = lambda: datetime(2026, 11, 25, 9, 2)
    cues.play = lambda *_a: None
    root = tk.Tk()
    noop = lambda *_a, **_k: None  # noqa: E731
    app = SimpleNamespace(root=root, config={"standup": {"hour": 9}}, desktop_escape=False, _quit=noop,
                          _toggle_rooms=noop, _toggle_chat=noop, _create_hud_win=noop, bots=None,
                          _chat_window=SimpleNamespace(_topic_id="moon-forge"), _chat_directory=lambda: str(data),
                          scanner=SimpleNamespace(get_agents=agents), _show_chat=noop)
    view = DungeonWindow(app)
    app.dungeon = view
    view.build(offscreen=True)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    view.set_left(False)
    view.set_right(False)
    view.show_center("dungeon")
    root.update()
    frames = []
    font = ImageFont.load_default(size=15)

    def shot():
        x, y = root.winfo_rootx(), root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def grab(text: str, hold: int = 1) -> None:
        image = shot()
        if text:
            draw = ImageDraw.Draw(image)
            w = int(draw.textlength(text, font=font)) + 28
            draw.rectangle((14, H - 48, 14 + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
            draw.text((28, H - 40), text, fill=(240, 230, 200), font=font)
        frames.extend([image] * hold)

    def room(seconds: float = 0.0) -> None:
        """Move the clock and draw the room at once (the tab draws on a worker thread)."""
        clock[0] += seconds
        throne = view.throne
        throne.stage.tick()
        if throne.stage.show is not None or seconds == 0.0:
            throne._frames = throne._art.render(throne.scene(), 1)
            throne._photos, throne._frame = {}, 0
            throne._draw()
        root.update()

    grab("09:02: the first Dungeon open of the day", 5)
    standup_panel.step(app)
    root.update()
    throne = view.throne
    throne.hide()
    throne.canvas.pack(fill="both", expand=True)
    root.update()
    room()
    grab("The orchestrator sounds the horn: standup in the throne room", 7)
    record = standup.latest(data)
    while throne.stage.show.frame(clock[0]).phase in ("horn", "gather"):
        room(STEP_S)
        grab("The agents with a task walk in through the hall door")
    stuck = next(i for i, e in enumerate(record["entries"]) if e["tone"] == "stuck")
    for i, entry in enumerate(record["entries"]):
        room(0.01)
        label = (f"{entry['name']}: stuck lines get the red wax" if i == stuck
                 else f"{entry['name']}: done and next, from the task summary")
        grab(label, 9 if i == stuck else 7)
        if i == stuck:
            shot().save(out / "desktop-1366.png")
        throne.stage.next()
    while throne.stage.show is not None and throne.stage.show.frame(clock[0]).phase == "return":
        room(STEP_S)
        grab("Space next, S skip, R replay, U call it again; then they walk back out")
    room(ss.WALK_S)
    card = next(e["card"] for e in record["entries"] if e["tone"] == "stuck")
    view.show_center("tasks")
    root.update()
    app._tasks_panel.open_card(card)
    root.update()
    grab("Each card gets the line as a note from Orrin: on the card and its room pin", 14)
    frames[0].save(out / "standup.gif", save_all=True, append_images=frames[1:], duration=180, loop=0, optimize=True)
    root.destroy()


if __name__ == "__main__":
    main()
