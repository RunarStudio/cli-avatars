"""MEMORY.1 evidence: the Memory tab, Remember from a chat line through Consolidate now, a pinned Topic room on the
map, and Settings > Bots with an inactive bot greyed and a pinned one.

The real app starts in-process on a temporary HOME, data folder, config.json and notes root (removed after), with
made-up notes and bots. The curator runs in-process on a throwaway repo with no remote, its commit made by git
plumbing (the fleet's git guard refuses porcelain commits outside its repos). Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x1080x24" python tools/shot_memory.py <out-dir>
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = Path(tempfile.mkdtemp(prefix="memory-shot-"))
for name in ("home", "data", "saves"):
    (_TMP / name).mkdir()
(_TMP / "gitconfig").write_text("[user]\n\tname = Notes Keeper\n\temail = keeper@example.invalid\n", encoding="utf-8")
os.environ.update(HOME=str(_TMP / "home"), USERPROFILE=str(_TMP / "home"), CLI_AVATARS_DATA_DIR=str(_TMP / "data"),
                  GIT_CONFIG_GLOBAL=str(_TMP / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
W, H = 1366, 768
TALL = 1080  # Settings tabs do not scroll: the bot list needs the height
NOTES = _TMP / "saves" / "memory"


def grab(height: int = H):
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=(0, 0, W, height), xdisplay=os.environ.get("DISPLAY")).convert("RGB")


def seed() -> None:
    """Made-up notes (two categories, three topics) and two bots: one fresh, one quiet for five hours."""
    from cli_avatars.app import memory_notes as mn
    from test_memory import commit, git

    mn.create(NOTES, ROOT / "tools" / "memory_curator.py")
    today = time.strftime("%Y-%m-%d")
    for cat, name, kind, updated, goal, nxt in (
            ("Garden", "tomatoes", "topic", today, "a red crop by July", "stake the vines"),
            ("Garden", "compost", "resource", "2026-01-04", "black gold by spring", "turn the heap"),
            ("Kitchen", "sourdough", "topic", "2026-02-10", "an open crumb", "feed the starter at 8")):
        folder = NOTES / "Topics" / cat
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text(
            f"---\ntype: {kind}\nname: {name}\ndescription: \ntopic: {cat}/{name}\nstatus: active\nupdated: {updated}\n"
            f"---\nGoal: {goal}\nStatus: active\nNext action: {nxt}\n\n## Log\n", encoding="utf-8")
    (NOTES / "Learnings" / "Kitchen.md").write_text("---\ntype: learning\nname: Kitchen\n---\n# Kitchen\n",
                                                    encoding="utf-8")
    git(NOTES, "init", "-q")
    commit(NOTES, "start")
    (_TMP / "config.json").write_text(json.dumps({"files": {"dir": str(_TMP / "saves")},
                                                  "sound": {"cues": False}}), encoding="utf-8")
    bots = _TMP / "data" / "bots"
    (bots / "local" / "status").mkdir(parents=True)
    (bots / "roster.json").write_text(json.dumps({"schema_version": 1, "groups": [
        {"id": "garden", "name": "Garden", "collapsed": False, "order": 0, "show_in_dungeon": True}], "bots": [
        {"id": "seed-sorter", "name": "Seed Sorter", "emoji": "", "group_id": "garden", "skin": "amongo"},
        {"id": "weed-watch", "name": "Weed Watch", "emoji": "", "group_id": "garden", "skin": "amongo"},
        {"id": "frost-alarm", "name": "Frost Alarm", "emoji": "", "group_id": "garden", "skin": "amongo",
         "always_show": True}]}), encoding="utf-8")
    (bots / "source.json").write_text(json.dumps({"kind": "folder", "folder": "local", "interval_s": 30}),
                                      encoding="utf-8")
    now = time.time()
    for slug, ago in (("seed-sorter", 600), ("weed-watch", 5 * 3600), ("frost-alarm", 9 * 3600)):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - ago))
        (bots / "local" / "status" / f"{slug}.json").write_text(json.dumps(
            {"schema_version": 1, "bot": slug, "state": "idle", "line": "watching", "updated_at": stamp}),
            encoding="utf-8")


def curator_in_process():
    """Consolidate now's start, with the fixture git (plumbing commit); everything else is the real curator."""
    import test_memory

    spec = importlib.util.spec_from_file_location("memory_curator", NOTES / "_app" / "memory_curator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.git = test_memory.fixture_git(module.git)

    def start(_python, _script, where) -> bool:
        module.run(Path(where))
        return True

    return start


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    seed()
    from cli_avatars.app import main as app_main
    from cli_avatars.app import memory_panel, shell
    import chat_window

    chat_window.start_curator = curator_in_process()
    shell.CONFIG_PATH = _TMP / "config.json"
    frames: list = []
    real_run = shell.OverlayApp.run

    def run(app) -> None:
        root = app.root
        root.after(200, lambda: root.geometry(f"{W}x{H}+0+0"))
        steps = []

        def at(seconds, fn):
            steps.append((seconds, fn))

        def frame():
            frames.append(grab().resize((W * 3 // 4, H * 3 // 4)))

        def panel():
            return app._memory_panel

        at(2.8, lambda: _quiet(app))
        at(3.0, lambda: app.dungeon.show_center("memory"))
        at(4.0, lambda: grab().save(out / "memory-tab.png"))
        at(4.2, frame)
        at(4.6, lambda: memory_panel.offer("Pinch the tomato suckers every Sunday", "chat:garden@09:10", "tomatoes"))
        at(5.2, frame)
        at(5.4, lambda: (panel().kind.set("todo"), panel().category.set("Garden")))
        at(5.8, frame)
        at(6.0, lambda: panel().save_button.invoke())
        at(6.6, frame)
        at(7.2, frame)
        at(7.6, lambda: panel().consolidate_button.invoke())
        at(8.0, frame)
        at(9.0, lambda: (setattr(panel(), "_at", 0), panel().watch(True), panel().refresh(force=True)))
        at(9.4, frame)
        at(10.0, lambda: (setattr(panel(), "selected", "Garden/tomatoes"), panel().refresh(force=True)))
        at(10.4, frame)
        at(10.8, frame)
        at(11.0, lambda: _pin(app))
        at(17.5, lambda: _go(app, "compost"))
        at(19.5, lambda: _marked(app, grab()).save(out / "topic-rooms.png"))
        at(19.8, lambda: root.geometry(f"{W}x{TALL}+0+0"))
        at(20.0, lambda: (app.dungeon.set_left(True), app.dungeon.set_right(True, "settings"), _bots_tab(app)))
        at(22.0, lambda: grab(TALL).save(out / "inactive-bots.png"))
        at(22.5, root.destroy)
        for seconds, fn in steps:
            root.after(int(seconds * 1000), fn)
        real_run(app)

    shell.OverlayApp.run = run
    try:
        app_main.main([])
    except SystemExit:
        pass
    if frames:
        frames[0].save(out / "remember.gif", save_all=True, append_images=frames[1:], duration=700, loop=0,
                       optimize=True)
    print(json.dumps(json.loads((NOTES / "_app" / "status.json").read_text(encoding="utf-8"))))
    return 0


def _quiet(app) -> None:
    """Close the first-run start check and the tour: this shot is about the Memory tab."""
    from cli_avatars.app import start_card, tour

    tour.maybe_start = lambda _app: None
    found = start_card.card(app)
    if found is not None:
        found.card.close()
    other = getattr(app, "_tour", None)
    if other is not None and other.alive():
        other.close()


def _pin(app) -> None:
    from cli_avatars.app import topic_rooms as tr
    from events import app_data_dir

    tr.set_pin(app_data_dir() / tr.PINS, "Garden/compost", True)
    app._memory_panel.refresh(force=True)


def _go(app, room: str) -> None:
    from cli_avatars.app import dungeon_nav

    app.dungeon.show_center("dungeon")
    app.dungeon.set_left(False)
    app.dungeon.set_right(False)
    app.root.update()
    if not dungeon_nav.jump(app, room):
        print(f"no room {room} on the map")
    dungeon_nav._button(app.dungeon, "fit")


def _marked(app, image):
    """The shot with each Topic room ringed and named (the map draws no room names)."""
    from PIL import ImageDraw

    from cli_avatars.app import topic_rooms as tr
    from cli_avatars.app.room_floor import Plan

    scene = app.dungeon.scene
    painter = scene._rooms_painter
    draw = ImageDraw.Draw(image)
    for room in painter.layout.get("rooms") or []:
        if tr.room_type(room) != tr.TOPIC:
            continue
        x, y = painter.to_canvas(*Plan.from_layout(painter.layout).floor(room["name"]).centre())
        x, y = x + scene.winfo_rootx(), y + scene.winfo_rooty()
        draw.ellipse((x - 70, y - 40, x + 70, y + 40), outline=(255, 214, 102), width=3)
        draw.text((x - 66, y - 62), f"Topic room: {room['name']} ({room['why']})", fill=(255, 214, 102))
    return image


def _bots_tab(app) -> None:
    from tkinter import ttk

    stack = [app.dungeon._settings]
    while stack:
        widget = stack.pop()
        if isinstance(widget, ttk.Notebook):
            for tab in widget.tabs():
                if widget.tab(tab, "text").strip() == "Bots":
                    widget.select(tab)
            return
        stack.extend(widget.winfo_children())


if __name__ == "__main__":
    try:
        code = main(Path(sys.argv[1]))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    raise SystemExit(code)
