"""SUMMON.1 + HIERARCHY.1 evidence: an empty Dungeon, the Summon plate, the throne room rising, the lord walking in,
the first message going out with the crown chip, then a topic room opening with its banner chip.

Made-up rooms, names and cards (the ORCH.ROOM stage of ``shot_orch_rooms``) in a temporary data folder, removed
after; the CLI is the tests' stub (``chat_ctx_fake``), never a real one. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_summon.py <out-dir>
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

_TOOLS = Path(__file__).resolve().parent
for _path in (_TOOLS, _TOOLS.parent / "tests"):
    sys.path.insert(0, str(_path))

import shot_orch_rooms as orch_shot  # noqa: E402
from shot_orch_rooms import caption  # noqa: E402

orch_shot.W, orch_shot.H, orch_shot.DOCK = 1366, 768, 470
EVERY, STEP = 0.1, 0.025


def seed_cards(_model) -> None:
    """Cards only: no session room is open, the Dungeon is the Apothecary alone."""
    from registry.facade import Registry
    from topics import ensure_topic

    reg = Registry(orch_shot._DATA)
    for topic in ("release-train", "harbor-map", "lantern-docs"):
        ensure_topic(orch_shot._DATA, topic, ts=1)
    for topic, title, column, _note in orch_shot.CARDS:
        card = reg.task_create(topic, title, topic=topic)
        if column != "todo":
            reg.task_move(card["id"], column)


def cursor(image, x: int, y: int):
    """A pixel arrow pointer at ``(x, y)``."""
    from PIL import ImageDraw

    out = image.copy()
    draw = ImageDraw.Draw(out)
    rows = ("1", "11", "121", "1221", "12221", "122221", "1222221", "12222221", "122211", "1211", "11")
    for dy, row in enumerate(rows):
        for dx, bit in enumerate(row):
            fill = (8, 6, 12) if bit == "1" else (255, 243, 200)
            draw.rectangle((x + dx * 2, y + dy * 2, x + dx * 2 + 1, y + dy * 2 + 1), fill=fill)
    return out


def main() -> None:
    import tkinter as tk

    from chat_ctx_fake import install
    from chat_window import ChatWindow
    from cli_avatars.app import cues, session_panel, summon
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.app.room_pane import RoomPane
    from cli_avatars.app.session_panel import SessionPanel
    from cli_avatars.model.room import save_binary_pin
    from cli_avatars.runner import cli_runner

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    work = orch_shot._DATA.parent / (orch_shot._DATA.name + "-work")
    for name in ("release-train", "harbor-map"):
        (work / name).mkdir(parents=True, exist_ok=True)
    played = []
    cues.play = lambda _app, name: played.append(name)
    orch_shot._seed = seed_cards
    orch_shot.load_sprites(orch_shot.REGISTRY)
    root = tk.Tk()
    root.geometry(f"{orch_shot.W}x{orch_shot.H}+0+0")
    stage = orch_shot.Stage(root)
    script = install(work)
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(script)))
    save_binary_pin(orch_shot._DATA, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
    app = stage.app
    summon.time = session_panel.time = SimpleNamespace(time=lambda: stage.clock[0])  # walks on the stage clock
    tk.Frame(stage.dock, bg="#0d0d1a", height=48).pack(fill="x")  # room for the caption
    panel = SessionPanel(app, stage.dock)
    panel.frame.pack(fill="x")
    host = tk.Frame(stage.dock, bg="#0d0d1a")
    host.pack(fill="both", expand=True)
    window = ChatWindow(root, directory=orch_shot._DATA, agents=[], config=app.config, container=host,
                        room_pane=RoomPane)
    app._chat_window = window
    app._show_chat = lambda topic_id=None, address_id=None: window.open(topic_id=topic_id)
    panel._ask_folder = lambda: str(work / "release-train")
    stage.tick(6.0)
    frames = []

    def film(seconds: float, text: str, point=None) -> None:
        for _ in range(max(1, round(seconds / EVERY))):
            stage.tick(EVERY, STEP)
            shot = caption(stage.grab(), text)
            frames.append(cursor(shot, *point) if point else shot)

    root.update()
    plate = (panel.summon_btn.winfo_rootx() - root.winfo_rootx() + panel.summon_btn.winfo_width() // 2,
             panel.summon_btn.winfo_rooty() - root.winfo_rooty() + panel.summon_btn.winfo_height() // 2)
    film(1.6, "No main orchestrator: the Dungeon is the Apothecary alone, the Summon plate shows")
    film(0.8, "Click Summon orchestrator (the first time it asks for the project folder once)", plate)
    panel.summon_btn.invoke()
    deadline = time.time() + 15
    while window._room._runs and time.time() < deadline:
        root.update()
        time.sleep(0.02)
    window._room._term.see("end")
    film(1.6, "The throne room rises; horn and hall bell (Windows; held in focus)")
    film(4.0, "Orrin, the summoned session, walks to the throne: the main orchestrator")
    film(2.4, "First message out with the crown chip: role + throne pack on stdin, --model fable --effort high")
    stage.grab().save(out / "desktop-1366.png")
    panel.kind.set(sr.SIMPLE)
    panel.folder = work / "harbor-map"
    panel.folder_label.config(text="harbor-map")
    film(1.0, "Sessions: Simple room, harbor-map, Open session")
    panel.open()
    film(1.6, "A topic room builds in: banner chip, fable high, hung under its door sign")
    film(6.0, "Vessa walks in: the topic orchestrator; task chats under it run opus medium")
    cli_runner.stop_all()
    frames[0].save(out / "summon.gif", save_all=True, append_images=frames[1:], duration=round(EVERY * 1000),
                   loop=0, optimize=True)
    root.destroy()
    shutil.rmtree(orch_shot._DATA, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    print("cues", played)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
