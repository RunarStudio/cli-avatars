"""START-SETUP.1 evidence: the start card with one missing folder fixed inline, New chat (back to a chat, a new one),
the first-run tour, the plain To: line and the whole window at 1366 px.

Made-up topics, avatars and folders in a temporary data folder, removed after; the CLI is a stub file that never runs;
PATH should be an empty folder. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_start_setup.py <out-dir>
    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_start_setup.py --address <repo root> <out.png>

The second form shoots only the composer's To: line with the chat code of ``<repo root>`` (an older tree gives "before").
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

_TMP = Path(tempfile.mkdtemp(prefix="start-setup-"))
_DATA = _TMP / "data"
_DATA.mkdir()
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
W, H, EVERY = 1366, 768, 0.1


def agents(now: float) -> list:
    """Two made-up orchestrators; one topic is addressed to an id that is no longer on the map."""
    row = dict(status="busy", source="claude", project="orchard", parent_id=None, last_seen=now, is_demo=False,
               failed=False, subagents=0)
    return [SimpleNamespace(agent_id="a1b2c3d4", name="Mira", skin="caine", **row),
            SimpleNamespace(agent_id="e5f6a7b8", name="Orrin", skin="bubble", **row)]


def seed_topics() -> None:
    from topics import join_topic, set_topic

    set_topic(_DATA, "west-keep", title="West keep", project="orchard", status="open", ts=300)
    set_topic(_DATA, "lantern", title="Lantern", project="orchard", status="open", ts=200)
    set_topic(_DATA, "moon-dock", title="Moon dock", project="harbor", status="open", ts=100)
    join_topic(_DATA, "west-keep", "a1b2c3d4", ts=300)
    join_topic(_DATA, "lantern", "f00d4e11", ts=200)


def caption(image, text: str):
    from PIL import ImageDraw

    out = image.copy()
    draw = ImageDraw.Draw(out)
    draw.rectangle((10, H - 44, 10 + 8 * len(text) + 24, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((22, H - 36), text, fill=(240, 230, 200))
    return out


def cursor(image, x: int, y: int):
    from PIL import ImageDraw

    out = image.copy()
    draw = ImageDraw.Draw(out)
    rows = ("1", "11", "121", "1221", "12221", "122221", "1222221", "12222221", "122211", "1211", "11")
    for dy, row in enumerate(rows):
        for dx, bit in enumerate(row):
            fill = (8, 6, 12) if bit == "1" else (255, 243, 200)
            draw.rectangle((x + dx * 2, y + dy * 2, x + dx * 2 + 1, y + dy * 2 + 1), fill=fill)
    return out


class Film:
    """Grabs the root while the Tk main loop runs (the boot check posts back with ``after``)."""

    def __init__(self, root) -> None:
        self.root = root
        self.frames: list = []

    def grab(self):
        from PIL import ImageGrab

        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def at(self, widget) -> tuple[int, int]:
        self.root.update()
        return (widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height() // 2)

    def roll(self, seconds: float, text: str, point=None, until=None) -> None:
        end = time.time() + seconds

        def shot():
            image = caption(self.grab(), text)
            self.frames.append(cursor(image, *point) if point else image)
            if time.time() >= end or (until is not None and until()):
                self.root.quit()
                return
            self.root.after(round(EVERY * 1000), shot)

        self.root.after(0, shot)
        self.root.mainloop()

    def save(self, path: Path) -> None:
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:], duration=round(EVERY * 1000), loop=0,
                            optimize=True)
        self.frames = []


def build(root):
    """The real Dungeon window (toolbar, docks, Sessions panel, chat dock) on a made-up host."""
    from bubbles import BubbleBoard
    from cli_avatars.app import chat
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.app.bootcheck import _ProbeHost
    from cli_avatars.app.dungeon_window import DungeonWindow
    from cli_avatars.app.session_panel import mount as mount_sessions

    host = _ProbeHost(root)
    host.scanner = SimpleNamespace(bubbles=BubbleBoard())
    host._chat_directory = lambda: _DATA
    host._rooms_records = lambda: agents(time.time())
    host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
    host._session_rooms.open(sr.SIMPLE, "claude", "west-keep")
    host._session_rooms.open(sr.SIMPLE, "claude", "lantern")
    host._chat_window = None
    host._ensure_chat_window = lambda: chat._ensure_chat_window(host)
    host._remember_chat_box = lambda box: None
    host._paint_chat_button = lambda: chat._paint_chat_button(host)
    host._show_chat = lambda topic_id=None, address_id=None: chat._show_chat(host, topic_id, address_id)
    host._status_parent = None
    host.dungeon = DungeonWindow(host)
    host.dungeon.build(offscreen=True)
    host._chat_host = host.dungeon._chat_host
    host.dungeon._offscreen = False
    host.dungeon._sessions = mount_sessions(host.dungeon)
    host._status_parent = __import__("tkinter").Frame(root, bg="#111018", height=24)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    host.dungeon.set_left(True)
    host._show_chat(topic_id="west-keep")
    root.update()
    return host


def main(out: Path) -> None:
    import tkinter as tk

    import repos
    from cli_avatars.app import cues, new_chat, start_card, tour
    from cli_avatars.app.bootcheck import start_bootcheck
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner

    out.mkdir(parents=True, exist_ok=True)
    played: list = []
    cues.play = lambda _app, name: played.append(name)
    start_card.CLOSE_MS = 1400
    seed_topics()
    stub = _TMP / "w" / "bin" / "claude"
    stub.parent.mkdir(parents=True)
    stub.write_bytes(b"\x7fELF stub")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", path=str(stub.parent)))
    save_binary_pin(_DATA, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
    harbor = _TMP / "w" / "harbor"
    harbor.mkdir()
    repos.add(_DATA, "Harbor", str(harbor))
    harbor.rmdir()
    root = tk.Tk()
    host = build(root)
    host._status_parent.pack(side="bottom", fill="x", before=root.winfo_children()[0])
    film = Film(root)

    # Start check: live rows, the Harbor folder is missing, Browse… picks it, Save, ✓, the card closes.
    start_bootcheck(host)
    card = start_card.card(host)
    tour.maybe_start = lambda _app: None  # the tour is filmed on its own below
    film.roll(3.0, "On launch the start card runs the checks live: spinner, then a mark and a reason",
              until=lambda: card.setup_done and time.time() > 0)
    film.roll(1.6, "Setup: the Harbor repo's folder is missing on disk, so the card stays open")
    moved = _TMP / "w" / "moved" / "harbor"
    moved.mkdir(parents=True)
    browse = [w for w in card.rows["repo:harbor"]["fix"].winfo_children() if str(w.cget("text")) == "Browse…"][0]
    save = [w for w in card.rows["repo:harbor"]["fix"].winfo_children() if str(w.cget("text")) == "Save"][0]
    film.roll(1.0, "Browse… opens the folder dialog", film.at(browse))
    card.browse("repo:harbor", ask=lambda _row: str(moved))
    film.roll(1.0, "Picked: harbor (only the folder name shows)", film.at(save))
    card.save("repo:harbor")
    film.roll(3.0, "Save writes the repo record, re-checks the row: ✓; nothing needs setup, so the card closes")
    film.save(out / "start-check.gif")

    # New chat: back to a chat in one click, then a new one.
    host._show_chat(topic_id="moon-dock")
    film.roll(1.0, "The chat shows Moon dock. Toolbar: New chat", film.at(host._new_chat_btn))
    card = new_chat.open_card(host)
    film.roll(1.6, "New chat: recent chats on top, one click goes back")
    first = card.recent_buttons[0]
    film.roll(0.8, "Click West keep", film.at(first))
    card.reach("west-keep")
    film.roll(1.4, "Back in West keep, To: Mira · West keep · Inbox")
    film.roll(0.8, "Or the composer's New chat", film.at(host._chat_window._new_chat_btn))
    card = new_chat.open_card(host)
    card.name.insert(0, "Moon Garden")
    card.project.insert(0, "orchard")
    film.roll(1.6, "+ New topic: Moon Garden in orchard; CLI Claude (Grok, Cursor greyed: set up)")
    film.grab().save(out / "desktop-1366.png")
    film.roll(0.8, "Start", film.at(card.start_btn))
    card.start()
    film.roll(2.0, "The chat opens on Moon Garden with Claude picked; pack cue. The CLI starts on Enter")
    film.save(out / "new-chat.gif")

    # Tour: every step points at the real control.
    t = tour.start(host)
    while t.alive():
        step = t.shown[-1]
        film.roll(1.8, f"First-run tour: {step.replace('_', ' ')}")
        t.next()
    film.roll(0.6, "Done: shown once, replay from Menu or Settings")
    film.save(out / "walkthrough.gif")
    root.destroy()
    print("cues", played)


def address(tree: Path, out: Path) -> None:
    """Only the composer's To: line, with the chat code of ``tree``, hovered so the tooltip shows."""
    sys.path.insert(0, str(tree))
    import tkinter as tk

    from chat_window import ChatWindow

    seed_topics()
    root = tk.Tk()
    root.geometry("700x600+0+0")
    root.configure(bg="#0d0d1a")
    from cli_avatars.app.dungeon_panes import install_fonts

    install_fonts(root)
    host = tk.Frame(root, bg="#0d0d1a", height=440)
    host.pack(fill="x")
    host.pack_propagate(False)  # the space under it is for the tooltip
    import inspect

    from cli_avatars.app.toolbar_widgets import hint

    extra = {"tip": hint} if "tip" in inspect.signature(ChatWindow).parameters else {}
    window = ChatWindow(root, directory=_DATA, agents=agents(time.time()), config={}, container=host, **extra)
    window.open(topic_id="lantern", address_id="f00d4e11")  # an agent no longer on the map
    root.update()
    tip = getattr(window._to_btn, "_kit_reason", "")
    if tip:
        window._to_btn.event_generate("<Enter>")
        end = time.time() + 0.6
        while time.time() < end:
            root.update()
            time.sleep(0.02)
    root.update()
    from PIL import ImageGrab

    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + 700, y + 600), xdisplay=os.environ.get("DISPLAY")).save(out)
    print(window._to_btn.cget("text"))
    root.destroy()


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--address":
            address(Path(sys.argv[2]), Path(sys.argv[3]))
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            main(Path(sys.argv[1]))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
