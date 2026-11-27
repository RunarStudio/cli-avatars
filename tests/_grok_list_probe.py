"""Child process for ``test_grok_topics``: Grok in the chat dock, the Grok topics strip, switching. Exit 77 without Tk.

    python tests/_grok_list_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. The ``grok_fake`` stub only: no real CLI, network or key.
"""

import json
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

from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, grok_topics, task_sessions  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.room import save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import close_logging  # noqa: E402
from grok_fake import install  # noqa: E402
from topics import set_topic, topic_messages  # noqa: E402

work = Path(sys.argv[2])
data, project = work / "data", work / "keep-repo"
project.mkdir(parents=True)
data.mkdir()


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


played = []
cues.play = lambda _app, name: played.append(name)
script = install(work)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script), templated=True))
save_binary_pin(data, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
set_working_dir(data, "west-keep", project, check=cli_runner.validate_working_dir)
window = ChatWindow(root, directory=data, agents=[], config=lambda: {}, offscreen=True, room_pane=RoomPane)
window.open(topic_id="west-keep")
pane = window._room
for _ in range(3):
    window.refresh(force=True)
    root.update()
toplevels = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
check("grok_chip_on_by_default", pane.chips["grok"].enabled, pane.chips["grok"].why)
pane.pick_target("inbox")
root.update()
check("strip_hidden_off_grok", not pane.grok.frame.winfo_ismapped())
pane.pick_target("grok")
root.update()
check("strip_shown_on_grok", pane.grok.frame.winfo_ismapped())


def turns() -> list[dict]:
    path = project / "fake-turns.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def send(text: str) -> dict:
    root.update()
    window._entry.insert(0, text)
    window._on_enter(SimpleNamespace())
    deadline = time.time() + 15
    while pane._runs and time.time() < deadline:
        root.update()
        time.sleep(0.02)
    root.update()
    return turns()[-1]


first = send("Which torch is out?")
sid = task_sessions.session(data, "west-keep", "grok")
check("enter_starts_grok_with_a_named_session", first["argv"][-2:] == ["-s", sid], first["argv"])
check("prompt_on_stdin_only", first["stdin"].endswith("Which torch is out?")
      and not any("torch" in a for a in first["argv"]))
transcript = pane._term.get("1.0", "end")
check("reply_streams_in_tagged_grok", "Grok › Grok turn 1: the west torches are lit." in transcript
      and "Grok › trim the wicks." in transcript, transcript[-400:])
check("send_and_reply_cues", played == ["grok-send", "grok-reply"], played)
second = send("And the east hall?")
check("next_message_resumes", second["argv"][-2:] == ["-r", sid], second["argv"])
check("one_row_for_the_room", [r["room"] for r in pane.grok.rows] == ["west-keep"], pane.grok.rows)

pane.grok.new_topic()
root.update()
check("new_topic_switches_the_composer", pane.room_id == "grok-1" and pane.target == "grok", pane.room_id)
third = send("A fresh thread on the gate")
check("new_topic_runs_in_the_bound_folder_with_its_own_session",
      third["argv"][-2] == "-s" and third["argv"][-1] != sid, third["argv"])
check("two_rows", sorted(r["room"] for r in pane.grok.rows) == ["grok-1", "west-keep"], pane.grok.rows)
pane.grok.pick("west-keep")
root.update()
check("click_switches_back", pane.room_id == "west-keep" and pane.target == "grok", pane.room_id)
check("history_kept_per_topic", "And the east hall?" in pane._term.get("1.0", "end")
      and "fresh thread" not in pane._term.get("1.0", "end"))
check("rows_carry_no_session_id", sid not in json.dumps(grok_topics.rows(data, live={})))
stored = [m["from"] for m in topic_messages(data, "grok-1") if m["from"] != "user"]
check("topic_lines_are_grok", stored and all(s.startswith("grok:") for s in stored), stored)
pane.grok.read_aloud()
if sys.platform != "win32":
    check("read_aloud_says_where_voice_is", "phone or browser" in window._status.cget("text"), window._status.cget("text"))
check("no_new_toplevel", len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]) == toplevels)

cli_runner.stop_all()
close_logging()
root.destroy()
print("done")
