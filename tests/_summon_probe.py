"""Child process for ``test_summon``: Summon in the Sessions panel and on the Throne tab. Exit 77 without Tk.

    python tests/_summon_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. A stub CLI only: no real CLI, network or key.
"""

import json
import subprocess  # noqa: TID251  # wraps Popen to count launches
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
try:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
except Exception:
    raise SystemExit(77)

from chat_ctx_fake import install  # noqa: E402
from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, summon, summon_ui, tiers  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.app.session_panel import SessionPanel  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402

work = Path(sys.argv[2])
data, project = work / "data", work / "high-keep"
project.mkdir(parents=True)
data.mkdir()


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


popen_calls = []
real_popen = subprocess.Popen


def counting_popen(*args, **kwargs):
    popen_calls.append(kwargs)
    return real_popen(*args, **kwargs)


subprocess.Popen = counting_popen
played = []
cues.play = lambda _app, name: played.append(name)
script = install(work)
config = {"orchestrator": {"main": "claude"}}
window = ChatWindow(root, directory=data, agents=[], config=lambda: config, offscreen=True, room_pane=RoomPane)
app = SimpleNamespace(config=config, places=None, _chat_directory=lambda: data, _chat_window=window,
                      _session_rooms=sr.SessionRooms(data / "ui" / "session_rooms.json"))
app._show_chat = lambda topic_id=None: window.open(topic_id=topic_id)
frame = tk.Frame(root)
panel = SessionPanel(app, frame)
panel.frame.pack()
throne = SimpleNamespace(app=app, canvas=tk.Canvas(frame, width=400, height=300))
throne.canvas.pack()
asked = []


def ask() -> str:
    asked.append(1)
    return str(project)


panel._ask_folder = ask
summon_ui.ask_folder = lambda _parent: ask()
root.update()


def shown(widget) -> bool:
    return bool(widget.winfo_manager())


def throne_button() -> bool:
    summon_ui.sync_throne(throne)
    items = throne.canvas.find_withtag(summon_ui.TAG)
    return bool(items) and throne.canvas.itemcget(items[0], "state") != "hidden"


check("button_shows_without_a_main", shown(panel.summon_btn) and throne_button())

panel.summon_btn.invoke()
root.update()
check("no_binary_starts_nothing_and_opens_no_room", not popen_calls and summon.wanted(app._session_rooms),
      popen_calls)
check("no_binary_says_why", "binary" in panel.status.cget("text").lower(), panel.status.cget("text"))

for cli in ("claude",):
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary(cli, finder=lambda _n: str(script)))
    save_binary_pin(data, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
asked.clear()
played.clear()
panel.summon_btn.invoke()
root.update()
check("one_click_one_process", len(popen_calls) == 1, popen_calls)
check("first_summon_asks_the_folder_once", asked == [1], asked)
kwargs = popen_calls[0]
argv = kwargs["args"]
check("fixed_argv_shell_false", kwargs["shell"] is False and isinstance(argv, list), kwargs.get("shell"))
check("main_tier_model_and_effort", argv[-4:] == ["--model", "fable", "--effort", "high"], argv)
check("opened_the_main_session", [(s.sid, s.kind) for s in app._session_rooms.sessions] == [("high-keep", "main")],
      app._session_rooms.sessions)
check("folder_in_the_room_file_only", load_room(data, "high-keep").working_dir == str(project.resolve()))
check("topic_remembered", summon.remembered(data) == "high-keep")
check("summon_cue", played[:1] == ["summon"], played)


def wait_done() -> None:
    deadline = time.time() + 15
    while time.time() < deadline:
        root.update()
        if not window._room._runs:
            return
        time.sleep(0.02)
    raise SystemExit("FAIL run did not finish")


wait_done()
turn = json.loads((project / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()[0])
check("prompt_on_stdin_is_the_role_and_pack", tiers.ROLE_HEAD in turn["stdin"] and summon.PACK_HEAD in turn["stdin"]
      and "main orchestrator" in turn["stdin"], turn["stdin"][:300])
check("prompt_not_in_argv", not any("orchestrator" in part for part in turn["argv"]))
panel.refresh()
root.update()
check("running_main_hides_the_button", not shown(panel.summon_btn) and not throne_button())
check("chat_shows_the_throne_room", window._topic_id == "high-keep" and window._room.target == "claude")

panel.end("high-keep")
app._session_rooms.live(time.time() + 60)
panel.refresh()
root.update()
check("ended_main_shows_it_again", shown(panel.summon_btn) and throne_button())
asked.clear()
summon_ui.sync_throne(throne)
throne.canvas.itemconfigure(summon_ui.TAG, state="normal")
summon_ui.click_throne(throne)
root.update()
check("later_summon_reuses_the_folder", asked == [] and len(popen_calls) == 2, (asked, len(popen_calls)))
wait_done()
check("throne_click_opens_the_main_again", not summon.wanted(app._session_rooms))
cli_runner.stop_all()
print("done")
