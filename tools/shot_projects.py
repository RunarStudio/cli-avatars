"""PROJECTS.1 evidence: the Projects tab in the real Dungeon window on a made-up host. The table, a row expanded
(tasks, topics, chats, repos, decisions), the column filter, then Start chat on a topic: the chat dock opens that
topic's chat with the CLI picked and the context as a draft. Nothing is sent and no CLI runs (the pinned CLI is a
stub file).

    CLI_AVATARS_DATA_DIR=<temp dir> xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_projects.py <out-dir>

Writes ``projects.gif``.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_park as sp  # noqa: E402
from PIL import ImageDraw, ImageGrab  # noqa: E402

W, H, EVERY = 1366, 768, 0.2


def seed() -> None:
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner
    from cli_avatars_mcp.projects import save_project
    from decisions import ask_decision
    from registry import task_chats
    from registry.facade import Registry

    sp.seed(sr.SessionRooms(sp._DATA / "ui" / "session_rooms.json"))
    save_project(sp._DATA, {"slug": "lantern", "name": "Lantern", "path": "/srv/made-up/lantern-works",
                            "repo_url": "https://example.invalid/guild/lantern-works", "status": "active",
                            "topics": [topic for topic, _kind, _title in sp.ROOMS]})
    save_project(sp._DATA, {"slug": "quiet-moth", "name": "Quiet Moth", "status": "idea"})
    reg = Registry(sp._DATA)
    seeds = next(c for c in reg.task_list("lantern") if c["title"] == "Sort the glass seeds")
    task_chats.start_chat(reg, seeds["id"], "claude")
    ask_decision(sp._DATA, agent="e5f6a7b8", room="glass-orchard", question="Copper or silver trim on the gate?",
                 options=["a=Copper", "b=Silver"])
    stub = sp._DATA / "stub-bin" / "claude"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_bytes(b"\x7fELF stub")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", path=str(stub.parent)))
    save_binary_pin(sp._DATA, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)


def build(root):
    """The real Dungeon window (toolbar, docks, chat dock) on a made-up host."""
    from bubbles import BubbleBoard
    from cli_avatars.app import chat
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.app.bootcheck import _ProbeHost
    from cli_avatars.app.dungeon_window import DungeonWindow

    host = _ProbeHost(root)
    host.scanner = SimpleNamespace(bubbles=BubbleBoard())
    host._chat_directory = lambda: sp._DATA
    host._rooms_records = lambda: []
    host._session_rooms = sr.SessionRooms(sp._DATA / "ui" / "session_rooms.json")
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
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    root.update()
    return host


def caption(image, text: str):
    out = image.copy()
    draw = ImageDraw.Draw(out)
    draw.rectangle((10, H - 44, 10 + 8 * len(text) + 24, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
    draw.text((22, H - 36), text, fill=(240, 230, 200))
    return out


def cursor(image, x: int, y: int):
    out = image.copy()
    draw = ImageDraw.Draw(out)
    rows = ("1", "11", "121", "1221", "12221", "122221", "1222221", "12222221", "122211", "1211", "11")
    for dy, row in enumerate(rows):
        for dx, bit in enumerate(row):
            fill = (8, 6, 12) if bit == "1" else (255, 243, 200)
            draw.rectangle((x + dx * 2, y + dy * 2, x + dx * 2 + 1, y + dy * 2 + 1), fill=fill)
    return out


class Film:
    def __init__(self, root) -> None:
        self.root, self.frames = root, []

    def at(self, widget) -> tuple[int, int]:
        self.root.update()
        return (widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height() // 2)

    def roll(self, seconds: float, text: str, point=None) -> None:
        for _ in range(max(1, round(seconds / EVERY))):
            self.root.update()
            time.sleep(EVERY / 2)
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            image = caption(ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY")), text)
            self.frames.append((cursor(image, *point) if point else image).convert("P", palette=0, colors=192))

    def save(self, path: Path) -> None:
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:], duration=round(EVERY * 1000), loop=0,
                            optimize=True)


def find(widget, test):
    if test(widget):
        return widget
    for child in widget.winfo_children():
        got = find(child, test)
        if got is not None:
            return got
    return None


def text_of(widget) -> str:
    try:
        return str(widget.cget("text"))
    except Exception:
        return ""


def main() -> None:
    import subprocess  # noqa: TID251  # disabled so the shot can start nothing
    import tkinter as tk

    from cli_avatars.app import cues, projects_panel

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cues.play = lambda _app, _name: None
    subprocess.Popen = None  # nothing may start a process here
    seed()
    root = tk.Tk()
    host = build(root)
    film = Film(root)
    view = host.dungeon
    view.show_center("projects")
    panel = projects_panel.ensure(view)
    film.roll(1.0, "Toolbar: the Projects tab", film.at(view._tab_projects))
    film.roll(2.0, "Projects: one row per project with its cards, topics, chats and repo folder")
    arrow = panel.rows["lantern"]["frame"].winfo_children()[0].winfo_children()[0]
    film.roll(1.0, "Open Lantern", film.at(arrow))
    panel.toggle("lantern")
    film.roll(3.0, "Lantern: tasks by column, topics, chats, repos, the newest decisions")
    film.roll(1.0, "Filter by column: doing", film.at(panel.chips["doing"]))
    panel.pick_column("doing")
    film.roll(2.4, "Only cards in doing")
    panel.pick_column("")
    row = find(panel.list, lambda w: text_of(w).strip().startswith("Glass orchard"))
    button = find(row.master, lambda w: text_of(w) == "Start chat")
    film.roll(1.2, "Start chat on the Glass orchard topic", film.at(button))
    panel.start("topic", "glass-orchard")
    film.roll(3.4, "The chat dock opens that topic's chat with Claude picked and the context drafted; nothing runs")
    film.save(out / "projects.gif")
    root.destroy()
    print("wrote projects.gif")


if __name__ == "__main__":
    main()
