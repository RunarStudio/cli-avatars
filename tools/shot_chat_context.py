"""CHAT-CTX.1 evidence: one task sends to Claude, Grok and Cursor; each starts with the pack, a second send resumes,
New session starts over, another task has its own sessions, Copy context.

Made-up tasks in a temporary data folder; one stub CLI stands in for all three (no real CLI, network or key). It
draws the real Dungeon window (chat dock) and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_chat_context.py <out-dir>

Writes ``chat-context.gif`` and ``desktop-1366.png``. ``serve`` runs the phone page on the same data for
``tools/shot_phone_sessions.js``.
"""

from __future__ import annotations

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
GROK = {"argv": ["--headless", "--json"], "resume": ["--session", "{session}"]}


def seed(data: Path, work: Path) -> dict:
    """Two made-up tasks with chats and a pack on the first; returns the rooms."""
    import context_packs
    from registry import task_chats
    from registry.facade import Registry
    from topics import set_topic

    set_topic(data, TOPIC, title="West keep", project=PROJECT, status="open")
    reg = Registry(data)
    torches = reg.task_create(PROJECT, "Light the west torches", topic=TOPIC,
                              body="Oil first, then wicks. Guide: https://lanterns.example/guide/wicks")
    hall = reg.task_create(PROJECT, "Sweep the east hall", topic=TOPIC)
    room = task_chats.start_chat(reg, torches["id"], "claude")[1]["room"]
    east = task_chats.start_chat(reg, hall["id"], "claude")[1]["room"]
    task_chats.apply_reply(data, room, ["TASK summary done: oiled both sconces | now: trimming wicks | "
                                        "next: light at dusk"], "ok")
    context_packs.pin(data, torches["id"], "decisions", "Use beeswax, never tallow")
    context_packs.pin(data, torches["id"], "files", "lamps/wick_trim.py")
    return {"torches": torches["id"], "room": room, "east": east}


def pin_stub(data: Path, base: Path) -> None:
    from chat_ctx_fake import install
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner

    script = install(base)
    for cli in ("claude", "grok", "cursor"):
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary(cli, finder=lambda _n: str(script), templated=True))
        save_binary_pin(data, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="ctx-shot-"))
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
    from cli_avatars.runner import cli_runner

    data, work = base / "data", base / "keep-repo"
    data.mkdir()
    work.mkdir()
    rooms = seed(data, work)
    pin_stub(data, base)
    cues.play = lambda *_a: None
    config = {"chat": {"clis": {"grok": GROK}}}
    root = tk.Tk()
    noop = lambda *_a, **_k: None  # noqa: E731
    app = SimpleNamespace(root=root, config=config, desktop_escape=False, _quit=noop, _toggle_rooms=noop,
                          _toggle_chat=noop, _create_hud_win=noop, bots=None, _chat_window=None,
                          _chat_directory=lambda: str(data), scanner=SimpleNamespace(get_agents=lambda: {}))

    def chat_window():
        if app._chat_window is None:
            app._chat_window = ChatWindow(root, directory=data, agents=[], config=config, container=app._chat_host,
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

    show_chat(TOPIC)
    window = chat_window()
    pane = window._room
    pane._ask_folder = lambda: str(work)
    pane.pick_target("claude")
    pane.pick_folder()  # the topic's folder, picked the way Daniel picks it
    show_chat(rooms["room"])
    app._tasks_panel.refresh(force=True)
    app._tasks_panel.open_card(rooms["torches"])
    grab("One task, one chat. Run: Inbox | Claude | Grok | Cursor, each in its own colour", 12)

    def send(cli: str, text: str, caption: str, after: str) -> None:
        pane.pick_target(cli)
        grab(caption, 5)
        for n in range(4, len(text) + 4, 4):
            window._entry.delete(0, "end")
            window._entry.insert(0, text[:n])
            grab(caption)
        window._on_enter(SimpleNamespace())
        deadline = time.time() + 15
        while pane._runs and time.time() < deadline:
            root.update()
            time.sleep(0.02)
        pane._term.see("end")
        grab(after, 12)

    send("claude", "Plan the wick trim", "Pick Claude, type, Enter",
         "Claude: a new session that starts with the task's pack, then the task")
    send("grok", "Second opinion on the wicks", "Same task, now Grok",
         "Grok: its own session, also started with the pack; replies tagged Grok ›")
    send("cursor", "Draft the dusk timer", "Same task, now Cursor",
         "Cursor: its own session with the pack; the three live in this one task chat")
    shot().save(out / "desktop-1366.png")
    send("claude", "Go on with step two", "Back to Claude",
         "Claude resumes this task's session: no pack again, just the task and the prompt")
    pane.pick_target("cursor")
    pane.new_session()
    grab("New session drops only Cursor's session", 10)
    send("cursor", "Start the timer over", "Cursor again", "A fresh Cursor session starts with the pack again")
    show_chat(rooms["east"])
    window.refresh(force=True)
    send("claude", "Sweep it", "Another task: Sweep the east hall",
         "Another task, its own sessions: Claude starts fresh with that task")
    show_chat(rooms["room"])
    window.refresh(force=True)
    pane._term.see("end")
    grab("Back to the torches: Claude, Grok and Cursor still resume here", 10)
    pane.copy_context()
    grab("Copy context: the same pack and task as text, for Grok on the web or the Cursor IDE", 14)
    cli_runner.stop_all()
    frames[0].save(out / "chat-context.gif", save_all=True, append_images=frames[1:], duration=160, loop=0,
                   optimize=True)
    root.destroy()


def serve() -> None:
    """The phone page on made-up data with sessions on the task; prints the pairing URL, serves until stdin closes."""
    import threading

    from cli_avatars.app import task_sessions
    from chat_ctx_fake import session
    from webui import auth, server

    base = Path(tempfile.mkdtemp(prefix="ctx-phone-"))
    try:
        data, work = base / "data", base / "keep-repo"
        data.mkdir()
        work.mkdir()
        rooms = seed(data, work)
        for cli, turns in (("claude", 3), ("grok", 1), ("cursor", 2)):
            for _ in range(turns):
                task_sessions.remember(data, rooms["room"], cli, session(cli, 1))
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    serve() if sys.argv[1:] == ["serve"] else main()
