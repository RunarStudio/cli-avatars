"""GROK-ORCH.1 evidence: the real Dungeon window on made-up data. New chat starts a Grok chat with nothing picked and
reopens one from the list grouped by project; the main orchestrator in Settings › Chat; Ask a bot on a task card (the
hand-off file, a made-up answer file, the answer on the card); a project's pages. Nothing runs: the Grok binary is
the ``grok_fake`` stub, pinned only, and ``subprocess.Popen`` is disabled.

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_grok_orch.py <out-dir>
    python tools/shot_grok_orch.py --serve    # the phone's server, for tools/shot_phone_grok_orch.js

Writes new-chat.gif, orchestrator-setting.png, ask-bot.gif, project-page.png, desktop-1366.png. The data dir is a
fresh temp folder, removed after.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

_TMP = Path(tempfile.mkdtemp(prefix="grok-orch-shot-"))
_DATA = _TMP / "data"
_DATA.mkdir()
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from shot_projects import Film, find, text_of  # noqa: E402

W, H = 1366, 768
SID = "d4e5f6a7-0000-4000-8000-00000000f00d"
ROSTER = {"schema_version": 1,
          "groups": [{"id": "garden", "name": "Garden", "collapsed": False, "order": 0},
                     {"id": "harbor", "name": "Harbor", "collapsed": False, "order": 1}],
          "bots": [{"id": f"{name.lower().replace(' ', '-')}", "name": name, "emoji": "", "group_id": group,
                    "skin": skin} for name, group, skin in (
              ("Moss Scout", "garden", "caine"), ("Lamp Keeper", "garden", "ponmi"), ("Seed Counter", "garden",
                                                                                       "bubble"),
              ("Tide Reader", "harbor", "caine"), ("Rope Mender", "harbor", "ponmi"))]}


def seed() -> dict:
    """Two projects, Grok chats in each (one resumes), a task with its Grok chat, the example bot roster."""
    from bots.roster import parse_roster, save_roster
    from cli_avatars.app import new_chat_model, task_sessions
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner
    from cli_avatars_mcp.projects import save_project
    from grok_fake import install
    from registry import task_chats
    from registry.facade import Registry
    from topics import ensure_topic, set_topic

    (_TMP / "w").mkdir(exist_ok=True)
    script = install(_TMP / "w")
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script), templated=True))
    save_binary_pin(_DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
    save_roster(_DATA / "bots" / "roster.json", parse_roster(ROSTER))
    save_project(_DATA, {"slug": "lantern", "name": "Lantern", "status": "active", "topics": ["glass-orchard"]})
    save_project(_DATA, {"slug": "harbor", "name": "Harbor", "status": "active", "topics": ["moon-dock"]})
    ensure_topic(_DATA, "glass-orchard", title="Glass orchard")
    ensure_topic(_DATA, "moon-dock", title="Moon dock")
    set_topic(_DATA, "moon-dock", project="harbor")
    for n, (project, title) in enumerate((("harbor", "Tide tables"), ("lantern", "Wick sizes"),
                                          ("lantern", "Glass colours"))):
        room, _ = new_chat_model.quick(_DATA, "grok")
        set_topic(_DATA, room, title=title, project=project, ts=time.time() - 3600 * (3 - n))
        task_sessions.remember(_DATA, room, "grok", SID[:-1] + str(n))
    reg = Registry(_DATA)
    card = reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
    reg.task_move(card["id"], "doing")
    reg.task_edit(card["id"], checklist=[{"text": "count the west row", "done": True},
                                         {"text": "weigh the basket", "done": False}])
    room = task_chats.start_chat(reg, card["id"], "grok")[1]["room"]
    gate = reg.task_create("lantern", "Fix the orchard gate", topic="glass-orchard")
    reg.task_move(gate["id"], "blocked")
    reg.task_progress(gate["id"], None, note="waiting on the smith")
    reg.task_create("lantern", "Paint the lamp posts", topic="glass-orchard")
    return {"card": reg.task_get(card["id"]), "room": room}


def build(root):
    """The real Dungeon window (toolbar, docks, chat dock) on a made-up host; Settings is the real config screen."""
    from bubbles import BubbleBoard
    from cli_avatars.app import chat, config_screen
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.app.bootcheck import _ProbeHost
    from cli_avatars.app.dungeon_window import DungeonWindow

    host = _ProbeHost(root)
    host.scanner = SimpleNamespace(bubbles=BubbleBoard(), get_agents=lambda: {})
    host.config = {}
    host._config_path = _DATA / "config.json"
    host._chat_directory = lambda: _DATA
    host._rooms_records = lambda: []
    host._session_rooms = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
    host._chat_window = None
    host._ensure_chat_window = lambda: chat._ensure_chat_window(host)
    host._remember_chat_box = lambda box: None
    host._paint_chat_button = lambda: chat._paint_chat_button(host)
    host._show_chat = lambda topic_id=None, address_id=None: chat._show_chat(host, topic_id, address_id)
    host._build_config_ui = lambda win: config_screen._build_config_ui(host, win)
    host._status_parent = None
    host.dungeon = DungeonWindow(host)
    host.dungeon.build(offscreen=True)
    host._chat_host = host.dungeon._chat_host
    host.dungeon._offscreen = False
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    root.update()
    return host


def note(image, title: str, lines: list[str]):
    """A paper slip over the frame: the file the app just wrote or read."""
    from PIL import ImageDraw

    out = image.copy()
    from PIL import ImageFont

    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=14)
    width = 20 + max(round(draw.textlength(line, font=font)) for line in (title, *lines))
    left = 420
    draw.rectangle((left, 120, left + width, 156 + 20 * len(lines)), fill=(238, 226, 196), outline=(90, 60, 30),
                   width=2)
    draw.text((left + 10, 128), title, fill=(120, 40, 20), font=font)
    for i, line in enumerate(lines):
        draw.text((left + 10, 152 + 20 * i), line, fill=(40, 28, 16), font=font)
    return out


def slip_to(card) -> None:
    """Scroll the task card so its Bot asks slip is in view."""
    card.frame.update()
    top = card.asks.title.winfo_rooty() - card.sheet.winfo_rooty()
    card.view.yview_moveto(max(0.0, (top - 40) / max(1, card.sheet.winfo_height())))
    card.frame.update()


def file_lines(path: Path, keys: tuple) -> list[str]:
    body = json.loads(path.read_text(encoding="utf-8"))
    return [f'"{k}": {json.dumps(body[k], ensure_ascii=False)[:60]}' for k in keys if k in body]


def main(out: Path) -> None:
    import subprocess  # noqa: TID251  # disabled so the shot can start nothing
    import tkinter as tk

    import bot_bridge
    from cli_avatars.app import bot_ask, cues, new_chat, project_pages, projects_panel

    out.mkdir(parents=True, exist_ok=True)
    played: list = []
    cues.play = lambda _app, name: played.append(name)
    subprocess.Popen = None  # nothing may start a process here
    seeded = seed()
    root = tk.Tk()
    host = build(root)
    film = Film(root)
    view = host.dungeon

    # Ask 1: New chat with nothing picked starts a Grok chat; the list reopens one by project and resumes it.
    host._show_chat(topic_id="moon-dock")
    film.roll(1.0, "Toolbar: New chat", film.at(host._new_chat_btn))
    card = new_chat.open_card(host)
    film.roll(2.4, "New chat: CLI is the main orchestrator (Grok); chats below, grouped by project, newest first")
    film.roll(1.0, "Nothing picked: Start", film.at(card.start_btn))
    card.start()
    film.roll(2.0, "A fresh Grok chat opens with Grok picked; it starts only on Enter")
    card = new_chat.open_card(host)
    film.roll(1.6, "Back to New chat: the new chat sits on top")
    row = next(r for r in card.recent if r["title"] == "Wick sizes")
    wick = next(b for b in card.recent_buttons if text_of(b).startswith("Wick sizes"))
    film.roll(1.0, "Click Wick sizes (lantern): it resumes its session", film.at(wick))
    card.reach(row["room"], row["cli"])
    film.roll(2.0, "Wick sizes reopens with Grok; the next send resumes its session (-r)")
    film.save(out / "new-chat.gif")

    # Ask 2: the main orchestrator in Settings › Chat.
    view.show_settings()
    root.update()
    notebook = find(view._settings, lambda w: w.winfo_class() == "TNotebook")
    tab = next(t for t in notebook.tabs() if notebook.tab(t, "text").strip() == "Chat")
    notebook.select(tab)
    film.roll(0.6, "Settings › Chat: the main orchestrator")
    host._orch_settings["chips"]["claude"].invoke()
    film.roll(0.6, "Switched live to Claude: saved in config.json, running chats untouched")
    host._orch_settings["chips"]["grok"].invoke()
    root.update()
    from PIL import ImageGrab

    def grab():
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    grab().save(out / "orchestrator-setting.png")
    film.frames = []
    view.set_right(False)

    # Ask 3: Ask a bot from the task card; the hand-off file; a made-up answer file lands on the card.
    view.show_center("tasks")
    panel = host._tasks_panel
    panel.open_card(seeded["card"]["id"])
    slip_to(panel.card_panel)
    film.roll(1.6, "Tasks: Count the glass apples; the Bot asks slip under the sandbox")
    film.roll(1.0, "Ask a bot…", film.at(panel.card_panel.asks.ask_btn))
    panel.card_panel.asks.ask_btn.invoke()
    picker = root._bot_picker
    film.roll(1.6, "The picker: every roster bot as Group · Name")
    picker.search.insert(0, "moss")
    picker._fill()
    film.roll(1.2, "Find: moss")
    picker.text.insert("1.0", "Which apples ripen first?")
    film.roll(1.2, "The ask", film.at(picker.send_btn))
    sent = picker.send()
    panel.card_panel.asks.tick()
    bridge = bot_bridge.root(_DATA, {})
    outbox = bridge / "outbox" / f"{sent['id']}.json"
    slip = file_lines(outbox, ("id", "bot", "group", "project", "card_title", "ask", "status"))
    slip_to(panel.card_panel)
    film.roll(2.6, "Send writes the hand-off file; the slip says pending")
    film.frames[-13:] = [note(f, f"bridge/outbox/{outbox.name}", slip) for f in film.frames[-13:]]
    second = bot_ask.open_picker(root, _DATA, card=seeded["card"]["id"])
    second.pick("tide-reader")
    second.text.insert("1.0", "Any beets near the orchard?")
    second.send()
    panel.card_panel.asks.tick()
    slip_to(panel.card_panel)
    film.roll(1.6, "A second ask to another bot: Bot asks (2 open)")
    inbox = bridge / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    answer = {"schema_version": 1, "id": sent["id"], "bot": "moss-scout", "answer": "The west row, by Friday.",
              "answered_at": "2026-11-26T10:00:00Z"}
    (inbox / outbox.name).write_text(json.dumps(answer), encoding="utf-8")
    bot_ask.step(host)
    panel.card_panel.asks.tick()
    panel.open_card(seeded["card"]["id"])
    slip_to(panel.card_panel)
    film.roll(3.4, "The other app writes inbox/<id>.json: answered on the card, a comment, the answer cue")
    film.frames[-17:-8] = [note(f, f"bridge/inbox/{outbox.name}", file_lines(inbox / outbox.name,
                                                                            ("id", "bot", "answer")))
                           for f in film.frames[-17:-8]]
    host._show_chat(topic_id=seeded["room"])
    film.roll(2.0, "And in the task's chat: Moss Scout answered")
    film.save(out / "ask-bot.gif")

    # Ask 4: the project's pages, next action first.
    view.show_center("projects")
    pages = projects_panel.ensure(view)
    pages.toggle("lantern")
    pages.toggle_more(seeded["card"]["id"])
    root.update()
    grab().save(out / "project-page.png")
    written = sorted(p.name for p in (_DATA / project_pages.FOLDER / "lantern").glob("*.md"))

    # The whole window: the throne room with the chat dock on Grok.
    view.show_center("throne")
    host._show_chat(topic_id="chat-1")
    root.update()
    time.sleep(0.4)
    grab().save(out / "desktop-1366.png")
    root.destroy()
    print("cues", played, "pages", written)


def serve() -> None:
    """The phone's side: the made-up data on 127.0.0.1 with writes on; prints the pairing URL, serves till stdin
    closes."""
    import threading

    from webui import auth, server

    seed()
    httpd = server.make_server(_DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(_DATA)}", flush=True)
    sys.stdin.read()
    httpd.shutdown()
    httpd.server_close()


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--serve":
            serve()
        else:
            main(Path(sys.argv[1]))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
