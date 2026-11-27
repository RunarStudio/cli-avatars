"""LEFTOVERS evidence: the first-start tour, the Memory tab with both side panels open, a Settings tab at its top and
after the wheel, and Topic rooms with their doors on a crowded map, all at 1366 x 768.

Reuses ``shot_memory``'s temporary HOME, data folder, config and made-up notes (removed after). Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_leftovers.py <out-dir> <label>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shot_memory as sm  # noqa: E402

W, H = sm.W, sm.H


def main(out: Path, label: str) -> int:
    out.mkdir(parents=True, exist_ok=True)
    sm.seed()
    from cli_avatars.app import main as app_main
    from cli_avatars.app import shell, start_card, tour

    shell.CONFIG_PATH = sm._TMP / "config.json"
    real_run = shell.OverlayApp.run

    def run(app) -> None:
        root = app.root
        root.after(200, lambda: root.geometry(f"{W}x{H}+0+0"))
        steps = []

        def at(seconds, fn):
            steps.append((seconds, fn))

        def first_start():
            found = start_card.card(app)
            if found is not None:
                found.card.close()
            app.dungeon.show_center("throne")
            tour.start(app)

        at(3.0, first_start)
        at(4.0, lambda: sm.grab().save(out / f"tour-{label}.png"))
        at(4.2, lambda: app._tour.close())
        at(4.4, lambda: (app.dungeon.set_left(True), app.dungeon.set_right(True, "chat"),
                         app.dungeon.show_center("memory")))
        at(5.4, lambda: sm.grab().save(out / f"memory-{label}.png"))
        at(5.6, lambda: (app.dungeon.set_right(True, "settings"), _settings_tab(app, "Chat")))
        at(6.6, lambda: sm.grab().save(out / f"settings-{label}-top.png"))
        at(6.8, lambda: _wheel(app, 30))
        at(7.6, lambda: sm.grab().save(out / f"settings-{label}-wheel.png"))
        at(7.8, lambda: _crowd(app))
        at(14.0, lambda: sm._go(app, "compost"))
        at(16.0, lambda: _doors(app, sm._marked(app, sm.grab())).save(out / f"topic-rooms-{label}.png"))
        at(16.5, root.destroy)
        for seconds, fn in steps:
            root.after(int(seconds * 1000), fn)
        real_run(app)

    shell.OverlayApp.run = run
    try:
        app_main.main([])
    except SystemExit:
        pass
    return 0


def _settings_tab(app, name: str) -> None:
    from tkinter import ttk

    stack = [app.dungeon._settings]
    while stack:
        widget = stack.pop()
        if isinstance(widget, ttk.Notebook):
            for tab in widget.tabs():
                if widget.tab(tab, "text").strip() == name:
                    widget.select(tab)
            return
        stack.extend(widget.winfo_children())


def _wheel(app, times: int) -> None:
    """Wheel down over the Settings panel as a hand would, on the widget under its middle."""
    root = app.root
    root.update()
    box = app.dungeon._settings
    x, y = box.winfo_rootx() + box.winfo_width() // 2, box.winfo_rooty() + box.winfo_height() // 2
    under = root.winfo_containing(x, y)
    for _ in range(times):
        if under is not None:
            under.event_generate("<Button-5>", x=5, y=5)
            under.event_generate("<MouseWheel>", delta=-120, x=5, y=5)
    root.update()


def _crowd(app) -> None:
    """A main and a simple session and all three made-up topics pinned: the Topic rooms hang off other rooms."""
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.app import topic_rooms as tr
    from events import app_data_dir

    app.dungeon.set_right(True, "chat")
    app._session_rooms.open(sr.MAIN, "claude", "moon-forge")
    app._session_rooms.open(sr.SIMPLE, "claude", "glass-orchard")
    for key in ("Garden/compost", "Garden/tomatoes", "Kitchen/sourdough"):
        tr.set_pin(app_data_dir() / tr.PINS, key, True)


def _doors(app, image):
    """The arch on each Topic room's anchor and the room's own door, marked: the walk goes through both."""
    from PIL import ImageDraw

    from cli_avatars.app import topic_rooms as tr
    from cli_avatars.app.room_floor import Plan

    scene = app.dungeon.scene
    painter = scene._rooms_painter
    plan = Plan.from_layout(painter.layout)
    draw = ImageDraw.Draw(image)
    for room in painter.layout.get("rooms") or []:
        if tr.room_type(room) != tr.TOPIC:
            continue
        for door, _forward in plan._hops("Apothecary", room["name"])[-2:]:
            x, y = painter.to_canvas(*door.path[1])
            x, y = x + scene.winfo_rootx(), y + scene.winfo_rooty()
            draw.rectangle((x - 9, y - 9, x + 9, y + 9), outline=(120, 220, 255), width=2)
    return image


if __name__ == "__main__":
    try:
        code = main(Path(sys.argv[1]), sys.argv[2])
    finally:
        shutil.rmtree(sm._TMP, ignore_errors=True)
    raise SystemExit(code)
