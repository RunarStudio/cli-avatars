"""CONTEXT-PACKS evidence: open a task card, its pack fills, pin a line, start a new chat that opens with the pack.

Made-up topic, card, decisions, files and links in a temporary data folder; a fake Claude answers (no real CLI,
network or key). It draws the real Dungeon window (Tasks tab, chat dock) and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_context_packs.py <out-dir>

Writes ``pack.gif`` and ``desktop-1366.png``. ``seed`` gives the same data for a phone shot.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _path in (_ROOT, _ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

W, H = 1366, 768
TOPIC, PROJECT = "west-keep", "lantern-works"
SESSION = "5e5e5e5e-0000-4000-8000-000000000001"
PIN = "Use beeswax, never tallow"
REPLY = "Both wicks trimmed to a finger's width.\n\nTASK summary done: wicks trimmed | now: waiting for dusk | next: light them"


def seed(data: Path) -> str:
    """The made-up task with a summary, two decisions, touched files and links; returns its card id."""
    import context_packs
    from cli_avatars.model.room import set_session_id
    from events import ActivityEvent
    from registry import task_chats
    from registry.facade import Registry
    from topics import set_topic

    set_topic(data, TOPIC, title="West keep", project=PROJECT, status="open")
    reg = Registry(data)
    card = reg.task_create(PROJECT, "Light the west torches", topic=TOPIC,
                           body="Oil first, then wicks. Guide: https://lanterns.example/guide/wicks")
    reg.task_comment(card["id"], "Oil chart: https://lanterns.example/oil-chart")
    _card, chat = task_chats.start_chat(reg, card["id"], "claude")
    set_session_id(data, chat["room"], "claude", SESSION)
    feed = context_packs.FileFeed(lambda: data)
    for name in ("sconce_oil.py", "wick_trim.py", "dusk_timer.md"):
        feed.on_event(ActivityEvent(source="claude", session_id=SESSION[:8], file=name, ts=time.time()))
    task_chats.apply_reply(data, chat["room"], ["TASK ask Clear or smoked glass? | Clear | Smoked",
                                                "TASK summary done: oiled both sconces | now: trimming wicks | "
                                                "next: light at dusk"], "ok")
    from registry.task_decisions import for_card

    reg.decision_answer(for_card(data, card["id"])[0]["id"], "b")
    task_chats.apply_reply(data, chat["room"], ["TASK ask Light at dusk or at the bell? | Dusk | Bell"], "ok")
    return card["id"]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="pack-shot-"))
    os.environ["CLI_AVATARS_DATA_DIR"] = str(base / "appdata")
    try:
        film(base, out)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir()) if p.is_file()))


def film(base: Path, out: Path) -> None:
    import tkinter as tk
    from types import SimpleNamespace

    from PIL import ImageDraw, ImageFont, ImageGrab

    from chat_window import ChatWindow
    from cli_avatars.app import cues
    from cli_avatars.app.dungeon_window import DungeonWindow
    from cli_avatars.app.room_pane import RoomPane
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner
    from room_chat_fake import install

    data, work = base / "data", base / "keep-repo"
    data.mkdir()
    work.mkdir()
    card_id = seed(data)
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(install(base))))
    save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
    (work / "fake-replies.json").write_text(json.dumps([REPLY]), encoding="utf-8")
    cues.play = lambda *_a: None
    root = tk.Tk()
    noop = lambda *_a, **_k: None  # noqa: E731
    app = SimpleNamespace(root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop,
                          _toggle_chat=noop, _create_hud_win=noop, bots=None, _chat_window=None,
                          _chat_directory=lambda: str(data), scanner=SimpleNamespace(get_agents=lambda: {}))

    def chat_window():
        if app._chat_window is None:
            app._chat_window = ChatWindow(root, directory=data, agents=[], config={}, container=app._chat_host,
                                          room_pane=RoomPane)
        return app._chat_window

    def show_chat(topic_id=None, address_id=None):
        view.set_right(True, "chat")
        chat_window().open(topic_id=topic_id)

    app._ensure_chat_window, app._show_chat = chat_window, show_chat
    view = DungeonWindow(app)
    app.dungeon = view
    view.build(offscreen=True)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    view.set_left(False)
    view.set_right(False)
    view.show_center("tasks")
    root.update()
    frames = []
    font = ImageFont.load_default(size=15)

    def shot():
        x, y = root.winfo_rootx(), root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def grab(text: str, hold: int = 1) -> None:
        for _ in range(3):
            root.update()
        image = shot()
        if text:
            draw = ImageDraw.Draw(image)
            w = int(draw.textlength(text, font=font)) + 28
            draw.rectangle((14, H - 48, 14 + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
            draw.text((28, H - 40), text, fill=(240, 230, 200), font=font)
        frames.extend([image] * hold)

    folder = chat_window()._room
    folder._ask_folder = lambda: str(work)
    folder.pick_target("claude")
    folder.pick_folder()  # the topic's folder, picked the way Daniel picks it
    panel = app._tasks_panel
    panel.refresh(force=True)
    grab("Tasks tab: one task in the West keep", 5)
    panel.open_card(card_id)
    grab("Open the card: its Context pack fills (summary, decisions, files, links)", 12)
    pack = panel.card_panel.pack
    pack.part.set("decisions")
    for n in range(3, len(PIN) + 3, 3):
        pack.entry.delete(0, "end")
        pack.entry.insert(0, PIN[:n])
        grab("Pin a line of your own")
    pack.pin_typed()
    grab("Pinned: a gold pin; pins go last when the 1,500-character cap drops lines", 12)
    panel.card_panel.chat_buttons["claude"].invoke()
    window = chat_window()
    pane = window._room
    pane._term.see("1.0")
    grab("New chat: marked 'starts with pack'; its first message is the pack, then the task", 14)
    shot().save(out / "desktop-1366.png")
    window._entry.insert(0, "Trim the wicks, please")
    window._on_enter(SimpleNamespace())
    deadline = time.time() + 15
    while pane._runs and time.time() < deadline:
        root.update()
        time.sleep(0.02)
    pane._term.see("1.0")
    grab("Enter: stdin gets the pack, the task, then your prompt (fixed argv, no shell)", 10)
    pane._term.see("end")
    window.refresh(force=True)
    grab("The reply updates the task; the room pin carries the satchel", 14)
    cli_runner.stop_all()
    frames[0].save(out / "pack.gif", save_all=True, append_images=frames[1:], duration=180, loop=0, optimize=True)
    root.destroy()


if __name__ == "__main__":
    main()
