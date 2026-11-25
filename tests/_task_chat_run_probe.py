"""Child process for ``test_task_chats``: a task chat in the room pane driving a fake Claude. Exit 77 without Tk.

    python tests/_task_chat_run_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. No real CLI, network or key.
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

from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.app.tasks_edit import TaskEditor  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import close_logging  # noqa: E402
from registry.facade import Registry  # noqa: E402
from room_chat_fake import install  # noqa: E402
from topics import set_topic, topic_messages  # noqa: E402

work = Path(sys.argv[2])
data = work / "data"
project = work / "keep-repo"
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
    popen_calls.append((args, kwargs))
    return real_popen(*args, **kwargs)


subprocess.Popen = counting_popen
script = install(work)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _name: str(script)))
save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
(project / "fake-replies.json").write_text(json.dumps(["Trimmed both wicks.\n\nTASK check 2\nTASK note Wicks trimmed"
                                                       "\nTASK check 9"]), encoding="utf-8")
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
editor = TaskEditor(data, "west-keep")
card = editor.create("Light the west torches", body="Oil first, then wicks.").card
for item in ("Oil the sconces", "Trim the wicks"):
    editor.check_add(card["id"], item)

window = ChatWindow(root, directory=data, agents=[], config={}, offscreen=True, room_pane=RoomPane)
window.open(topic_id="west-keep")
pane = window._room
pane._ask_folder = lambda: str(project)
pane.pick_target("claude")
pane.pick_folder()
check("parent_room_has_its_folder", load_room(data, "west-keep").working_dir == str(project.resolve()))

out = editor.chat_new(card["id"], "claude")
room = out.card["chats"][0]["room"]
window.open(topic_id=room)
for _ in range(3):
    window.refresh(force=True)
    root.update()
check("new_chat_starts_nothing", not popen_calls, popen_calls)
check("chat_targets_claude", pane.cli_target() == "claude")
text = pane._term.get("1.0", "end")
check("chat_shows_task_context", "Light the west torches" in text and "2. [ ] Trim the wicks" in text, text)

pane._ask_folder = lambda: (_ for _ in ()).throw(AssertionError("folder dialog opened"))
window._entry.insert(0, "Trim the wicks please")
window._on_enter(SimpleNamespace())
deadline = time.time() + 15
while pane._runs and time.time() < deadline:
    root.update()
    time.sleep(0.02)
check("enter_starts_one_process_in_the_parent_folder", len(popen_calls) == 1
      and popen_calls[0][1].get("cwd") == str(project.resolve()), popen_calls)
check("chat_room_stores_no_folder", load_room(data, room).working_dir == "")
turn = json.loads((project / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()[0])
stdin = turn["stdin"]
check("stdin_has_task_context_before_prompt", stdin.endswith("Trim the wicks please")
      and stdin.index("[cli-avatars task context") < stdin.index("Trim the wicks please")
      and "2. [ ] Trim the wicks" in stdin, stdin)
fresh = Registry(data).task_get(card["id"])
check("reply_ticks_its_own_task", fresh["checklist"][1]["done"] and fresh["status_note"] == "Wicks trimmed",
      fresh["checklist"])
text = pane._term.get("1.0", "end")
check("transcript_shows_task_updates", "✓ task: ticked 2" in text and "✓ task: refused check 9" in text, text)
lines = [m["text"] for m in topic_messages(data, "west-keep")]
check("parent_topic_hears_the_update", any(f"claude:{room}" in t and "ticked Trim the wicks" in t for t in lines),
      lines)
cli_runner.stop_all()
close_logging(data)
root.destroy()
print("done")
