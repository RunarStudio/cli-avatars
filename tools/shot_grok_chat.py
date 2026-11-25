"""GROK-CHAT.1 evidence: Grok picked on the Run row, the Grok topics strip, a message typed, the reply streaming in
Grok's blue, a new Grok topic, then a click back to the first topic.

Made-up rooms and cards (the ORCH.ROOM stage of ``shot_orch_rooms``) in a temporary data folder, removed after; Grok
is a slow stub written here (made-up replies, word by word), never a real CLI. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_grok_chat.py <out-dir>
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
from shot_summon import cursor, seed_cards  # noqa: E402

orch_shot.W, orch_shot.H, orch_shot.DOCK = 1366, 768, 520
EVERY, STEP = 0.1, 0.025

SLOW_GROK = """\
#!/usr/bin/env python3
import json
import sys
import time

args = sys.argv[1:]
prompt = sys.stdin.read()
session = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-r", "-s")), "")
if "gate" in prompt.strip().splitlines()[-1]:
    words = "The north gate build is green. Two flaky checks remain; I would pin the clock in both first.".split()
else:
    words = ("The release train leaves at nine. Blocker: the harbor map tiles are not signed yet."
             " Next: sign the tiles, then tag the build.").split()


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


emit({"type": "session_start", "sessionId": session})
emit({"sessionUpdate": "tool_call", "title": "read_file"})
for word in words:
    time.sleep(0.09)
    emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": word + " "}})
    if word.endswith("."):
        emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "\\n"}})
emit({"type": "result", "stopReason": "end_turn", "sessionId": session})
"""


def main() -> None:
    import tkinter as tk

    from chat_window import ChatWindow
    from cli_avatars.app import cues
    from cli_avatars.app.room_pane import RoomPane
    from cli_avatars.model.room import save_binary_pin, set_working_dir
    from cli_avatars.runner import cli_runner
    from grok_fake import install

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    work = orch_shot._DATA.parent / (orch_shot._DATA.name + "-work")
    work.mkdir(parents=True, exist_ok=True)
    played = []
    cues.play = lambda _app, name: played.append(name)
    orch_shot._seed = seed_cards
    orch_shot.load_sprites(orch_shot.REGISTRY)
    root = tk.Tk()
    root.geometry(f"{orch_shot.W}x{orch_shot.H}+0+0")
    stage = orch_shot.Stage(root)
    script = install(work)
    (work / "fake-claude").write_text(SLOW_GROK, encoding="utf-8", newline="\n")
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script), templated=True))
    save_binary_pin(orch_shot._DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
    for room in ("release-train", "harbor-map"):
        (work / room).mkdir()
        set_working_dir(orch_shot._DATA, room, work / room, check=cli_runner.validate_working_dir)
    tk.Frame(stage.dock, bg="#0d0d1a", height=48).pack(fill="x")  # room for the caption
    host = tk.Frame(stage.dock, bg="#0d0d1a")
    host.pack(fill="both", expand=True)
    window = ChatWindow(root, directory=orch_shot._DATA, agents=[], config=stage.app.config, container=host,
                        room_pane=RoomPane)
    window.open(topic_id="release-train")
    pane = window._room
    stage.tick(4.0)
    frames = []

    def film(seconds: float, text: str, point=None) -> None:
        for _ in range(max(1, round(seconds / EVERY))):
            stage.tick(EVERY, STEP)
            shot = caption(stage.grab(), text)
            frames.append(cursor(shot, *point) if point else shot)

    def at(widget) -> tuple[int, int]:
        root.update()
        return (widget.winfo_rootx() - root.winfo_rootx() + min(60, widget.winfo_width() // 2),
                widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() // 2)

    def type_and_send(text: str, note: str) -> None:
        for i in range(0, len(text), 3):
            window._entry.insert("end", text[i:i + 3])
            film(EVERY, note)
        window._on_enter(SimpleNamespace())
        deadline = time.time() + 30
        while pane._runs and time.time() < deadline:
            pane._term.see("end")
            film(EVERY, "Grok answers: the reply streams in as Grok lines in its blue (send cue)")
        pane._term.see("end")
        film(1.6, "Done: reply cue (Windows, held in focus); the next message resumes this Grok session")

    root.update()
    film(1.4, "A room chat: the Run row offers Inbox | Claude | Grok | Cursor")
    film(0.8, "Pick Grok: it ships a default command from the Grok Build docs", at(pane.chips["grok"]))
    pane.pick_target("grok")
    film(1.4, "The Grok topics strip opens over the composer")
    type_and_send("Where is the release train?", "Type a message, press Enter (prompt on stdin, never in argv)")
    stage.grab().save(out / "desktop-1366.png")
    new_btn = [w for w in pane.grok.frame.winfo_children()[0].winfo_children() if isinstance(w, tk.Button)][-1]
    film(1.0, "+ New Grok topic: a fresh Grok conversation bound to this room's folder", at(new_btn))
    pane.grok.new_topic()
    film(1.2, "The composer switches to the new topic: its own history, its own session")
    type_and_send("Is the north gate build green?", "Ask the new topic")
    root.update()
    rows = pane.grok.body.winfo_children()
    film(1.2, "Click the first topic's row to switch back", at(rows[1]) if len(rows) > 1 else None)
    pane.grok.pick("release-train")
    pane._term.see("end")
    film(2.4, "Back on the release train: its history and Grok session resume")
    cli_runner.stop_all()
    frames[0].save(out / "grok-chat.gif", save_all=True, append_images=frames[1:], duration=round(EVERY * 1000),
                   loop=0, optimize=True)
    root.destroy()
    shutil.rmtree(orch_shot._DATA, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    print("cues", played)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
