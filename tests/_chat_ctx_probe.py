"""Child process for ``test_chat_context``: one task sends to Claude, Grok and Cursor from the composer. Exit 77 without Tk.

    python tests/_chat_ctx_probe.py <repo root> <work root>

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

import context_packs  # noqa: E402
import focus  # noqa: E402
from chat_ctx_fake import install, session  # noqa: E402
from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues, task_sessions  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.room import save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import close_logging  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
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


popen_calls = []
real_popen = subprocess.Popen


def counting_popen(*args, **kwargs):
    popen_calls.append(kwargs.get("args", args[0] if args else None))
    return real_popen(*args, **kwargs)


subprocess.Popen = counting_popen
played = []
cues.play = lambda _app, name: played.append(name)
script = install(work)
for cli in ("claude", "grok", "cursor"):
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary(cli, finder=lambda _n: str(script), templated=True))
    save_binary_pin(data, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
set_working_dir(data, "west-keep", project, check=cli_runner.validate_working_dir)
reg = Registry(data)
torches = reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
hall = reg.task_create("keep-demo", "Sweep the east hall", topic="west-keep")
context_packs.pin(data, torches["id"], "decisions", "Use beeswax, never tallow")
room = task_chats.start_chat(reg, torches["id"], "claude")[1]["room"]
room2 = task_chats.start_chat(reg, torches["id"], "claude")[1]["room"]
east = task_chats.start_chat(reg, hall["id"], "claude")[1]["room"]
config = {"chat": {"clis": {"grok": {"argv": ["--headless", "--json"], "resume": ["--session", "{session}"]}}}}

window = ChatWindow(root, directory=data, agents=[], config=lambda: config, offscreen=True, room_pane=RoomPane)
window.open(topic_id=room)
pane = window._room
for _ in range(3):
    window.refresh(force=True)
    root.update()
check("run_row_offers_four", list(pane.chips) == ["inbox", "claude", "grok", "cursor"], list(pane.chips))
check("found_and_configured_are_enabled", all(pane.chips[k].enabled for k in pane.chips))


def turns() -> list[dict]:
    path = project / "fake-turns.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def send(cli: str, text: str) -> dict:
    pane.pick_target(cli)
    root.update()
    before = len(popen_calls)
    window._entry.insert(0, text)
    window._on_enter(SimpleNamespace())
    deadline = time.time() + 15
    while pane._runs and time.time() < deadline:
        root.update()
        time.sleep(0.02)
    root.update()
    check(f"{cli}_{len(turns())}_one_process", len(popen_calls) == before + 1, popen_calls[before:])
    return turns()[-1]


def packed(turn: dict, title: str = "Light the west torches") -> bool:
    stdin = turn["stdin"]
    return (context_packs.HEAD in stdin and "Use beeswax" in stdin
            and stdin.index(context_packs.HEAD) < stdin.index("[cli-avatars task context")
            < stdin.index(f"title: {title}"))


check("picking_starts_nothing", [pane.pick_target(k) for k in ("claude", "grok", "cursor")] and not popen_calls)
first = send("claude", "Plan the wicks")
check("claude_fresh_with_pack", "--resume" not in first["argv"] and packed(first), first)
check("pack_cue_on_a_fresh_session", played == ["pack"], played)
grok = send("grok", "Second view on the wicks")
check("grok_template_argv", grok["cli"] == "grok" and grok["argv"] == ["--headless", "--json"], grok["argv"])
check("grok_fresh_with_pack", packed(grok), grok["stdin"][:200])
cursor = send("cursor", "Draft the timer")
check("cursor_default_argv", cursor["argv"] == ["-p", "--output-format", "stream-json", "--mode", "plan"],
      cursor["argv"])
check("cursor_fresh_with_pack", packed(cursor))
check("prompts_stay_on_stdin", all(not any("wicks" in a or "timer" in a for a in t["argv"]) for t in turns()))
again = send("claude", "Go on")
check("claude_resumes_its_session", again["argv"][-2:] == ["--resume", session("claude", 1)], again["argv"])
check("resume_has_task_not_pack", context_packs.HEAD not in again["stdin"]
      and "[cli-avatars task context" in again["stdin"])
check("no_pack_cue_on_resume", played == ["pack"] * 3, played)
check("one_session_per_cli", [task_sessions.session(data, room, c) for c in ("claude", "grok", "cursor")]
      == [session("claude", 1), session("grok", 2), session("cursor", 3)])
grok2 = send("grok", "And?")
check("grok_resumes_with_its_flag", grok2["argv"][-2:] == ["--session", session("grok", 2)], grok2["argv"])

text = pane._term.get("1.0", "end")
check("replies_tagged_by_source", all(f"{n} › {c} turn" in text for n, c in
                                      (("Claude", "claude"), ("Grok", "grok"), ("Cursor", "cursor"))), text)
senders = {m["from"] for m in topic_messages(data, room)}
check("replies_land_in_the_task_chat", {"claude:room", "grok:room", "cursor:room"} <= senders, senders)

pane.pick_target("cursor")
pane.new_session()
check("new_session_drops_only_cursor", task_sessions.session(data, room, "cursor") is None
      and task_sessions.session(data, room, "claude") == session("claude", 1))
fresh = send("cursor", "Start over")
check("new_session_starts_with_pack", "--resume" not in fresh["argv"] and packed(fresh))

window.open(topic_id=east)
for _ in range(2):
    window.refresh(force=True)
    root.update()
check("target_kept_on_switch", pane.cli_target() == "cursor")
hall_turn = send("claude", "Sweep it")
check("switch_task_switches_sessions", "--resume" not in hall_turn["argv"]
      and packed(hall_turn, "Sweep the east hall") is False and "Sweep the east hall" in hall_turn["stdin"]
      and "Light the west torches" not in hall_turn["stdin"], hall_turn["stdin"][:300])
window.open(topic_id=room2)
root.update()
back = send("claude", "Back to the torches")
check("same_task_other_chat_resumes", back["argv"][-2:] == ["--resume", session("claude", 1)], back["argv"])

calls = len(popen_calls)
focus.start(data, torches["id"])
played.clear()
pane.copy_context()
clip = root.clipboard_get()
check("copy_context_is_the_pack_and_task", clip.startswith(context_packs.HEAD) and "title: Light the west torches"
      in clip and "Use beeswax" in clip, clip[:200])
check("copy_is_quiet_in_focus", played == [], played)
check("copy_starts_nothing", len(popen_calls) == calls)

config["chat"] = {}
pane.refresh_clis()
root.update()
grey = pane.chips["grok"]
check("unset_grok_greyed_with_hint", not grey.enabled and "chat.clis.grok.argv" in grey.why, grey.why)
pane.pick_target("claude")
pane.pick_target("grok")
check("greyed_chip_does_not_pick", pane.cli_target() == "claude")
check("no_process_without_enter", len(popen_calls) == calls)
cli_runner.stop_all()
close_logging(data)
root.destroy()
print("done")
