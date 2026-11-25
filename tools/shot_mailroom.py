"""MAILROOM evidence: three letters arrive, the sorter proposes, one is approved, one retopiced, one bounced.

Made-up topics, cards and letters in a temporary data folder; no real session, chat or board is read. It draws
the real Dungeon window with the Mailroom tab and the Needs you dock, and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_mailroom.py <out-dir>

Writes ``mailroom.gif`` and ``desktop-1366.png``. ``seed`` gives the same data for a phone shot.
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

W, H = 1366, 768
TOPICS = (("moon-forge", "Moon forge", "Polish the moon gate"), ("glass-orchard", "Glass orchard", "Count the glass apples"),
          ("ember-ledger", "Ember ledger", "Balance the ember ledger"))
PROJECT = "lantern"


def seed(data: Path) -> None:
    from registry.facade import Registry
    from topics import set_topic

    reg = Registry(data)
    for topic, title, card in TOPICS:
        set_topic(data, topic, title=title, project=PROJECT, status="open")
        reg.task_create(PROJECT, card, topic=topic)


def letters(data: Path) -> list:
    """The three arrivals, as callables, oldest first."""
    import mailroom
    from events import append_channel

    def say(room, sender, text, to):
        entry = {"ts": time.time(), "from": sender, "to": to, "channel": room, "icon": "speech", "note": text}
        if to == "user":
            entry["kind"] = "msg"
        append_channel(data, entry)

    return [lambda: mailroom.post(data, "Count the glass apples again before the frost"),
            lambda: say("ember-ledger", "claude:a1b2c3d4", "Should the ember ledger close weekly or monthly?", "user"),
            lambda: say("moon-forge", "claude:e5f6a7b8", "Hinges polished. Fix the cracked lantern by the gate next?",
                        "claude:e5f6a7b8")]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="mailroom-shot-"))
    os.environ["CLI_AVATARS_DATA_DIR"] = str(data)
    try:
        film(data, out)
    finally:
        shutil.rmtree(data, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


def film(data: Path, out: Path) -> None:
    import tkinter as tk
    from types import SimpleNamespace

    from PIL import ImageDraw, ImageFont, ImageGrab

    import mailroom
    from cli_avatars.app import cues, mail_panel, needs_panel
    from cli_avatars.app.dungeon_window import DungeonWindow

    seed(data)
    mailroom.ingest(data, now=time.time() - 60)
    root = tk.Tk()
    cues.play = lambda *_a: None
    noop = lambda *_a, **_k: None  # noqa: E731
    app = SimpleNamespace(root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop,
                          _toggle_chat=noop, _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="moon-forge"),
                          _chat_directory=lambda: str(data), scanner=SimpleNamespace(get_agents=lambda: {}),
                          _show_chat=noop)
    view = DungeonWindow(app)
    app.dungeon = view
    view.build(offscreen=True)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    view.set_left(False)
    view.set_right(True, "needs")
    view.show_center("mailroom")
    root.update()
    panel = app._mail_panel
    frames = []
    font = ImageFont.load_default(size=15)

    def tick() -> None:
        app._mail_gate = app._needs_gate = None
        mail_panel.step(app)
        needs_panel.step(app)
        root.update()

    def grab(text: str, hold: int = 1) -> None:
        tick()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        shot = ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))
        if text:
            draw = ImageDraw.Draw(shot)
            w = int(draw.textlength(text, font=font)) + 28
            draw.rectangle((14, H - 48, 14 + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
            draw.text((28, H - 40), text, fill=(240, 230, 200), font=font)
        frames.extend([shot] * hold)

    grab("The Mailroom: nothing to sort", 4)
    for at, (arrive, text) in enumerate(zip(letters(data), (
            "A thought sent with Ctrl+Space > Mail lands as a letter; the sorter picks Glass orchard",
            "An agent's message: a question, so the sorter drafts a decision",
            "A hook note ending in a question: a draft decision, and 'Fix' proposes a task chat"))):
        arrive()
        grab(text, 6)
        if at == 2:
            grab("Three letters: shelf and sack fill, Needs you shows one Mailroom row", 4)
    ids = panel.ids()
    panel.selected = ids[0]
    panel._place()
    grab("Enter (or A) approves the selected letter", 4)
    panel.approve()
    grab("Filed: one card in Glass orchard, as Daniel", 6)
    panel.selected = ids[2]
    panel._place()
    grab("T: the next topic the ranker gives", 3)
    panel.next_topic()
    grab("Topic changed before filing", 6)
    panel.selected = ids[1]
    panel._place()
    grab("B bounces: the letter moves to Unsorted (a second B drops it)", 3)
    panel.bounce()
    grab("Bounced to Unsorted; nothing was filed for it", 8)
    panel.selected = ids[2]
    panel._place()
    tick()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY")).save(out / "desktop-1366.png")
    frames[0].save(out / "mailroom.gif", save_all=True, append_images=frames[1:], duration=350, loop=0,
                   optimize=True)
    root.destroy()


if __name__ == "__main__":
    main()
