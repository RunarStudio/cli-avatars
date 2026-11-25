"""Child process for ``test_context_packs``: the Pack slip on a card and a new chat that starts with it. Exit 77 without Tk.

    python tests/_pack_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. A fake Claude answers: no real CLI, network or key.
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
except Exception:
    raise SystemExit(77)

import context_packs  # noqa: E402
from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.app.tasks_edit import TaskEditor  # noqa: E402
from cli_avatars.model.room import save_binary_pin, set_session_id  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import ActivityEvent, close_logging  # noqa: E402
from registry import task_chats  # noqa: E402
from room_chat_fake import install  # noqa: E402
from topics import set_topic  # noqa: E402

work = Path(sys.argv[2])
data, project = work / "data", work / "keep-repo"
project.mkdir(parents=True)
data.mkdir()


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


popen_calls, played = [], []
real_popen = subprocess.Popen


def counting_popen(*args, **kwargs):
    popen_calls.append((args, kwargs))
    return real_popen(*args, **kwargs)


subprocess.Popen = counting_popen
cues.play = lambda app, name: played.append(name)
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
editor = TaskEditor(data, "west-keep")
card = editor.create("Light the west torches", body="Guide: https://lanterns.example/wicks").card
first = editor.chat_new(card["id"], "claude").card["chats"][0]["room"]
set_session_id(data, first, "claude", "5e5e5e5e-0000-4000-8000-000000000001")
context_packs.FileFeed(lambda: data).on_event(ActivityEvent(source="claude", session_id="5e5e5e5e", file="wick.py"))
task_chats.apply_reply(data, first, ["TASK ask Beeswax or tallow? | Beeswax | Tallow",
                                     "TASK summary done: oiled | now: trimming | next: light at dusk"], "ok")

chat = SimpleNamespace(_topic_id="west-keep")
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=chat, _chat_directory=lambda: data,
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=noop,
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1200x720+0+0")
root.update()
view.show_center("tasks")
root.update()
panel = app._tasks_panel
panel.open_card(card["id"])
root.update()
pack = panel.card_panel.pack
texts = {part: [x["text"] for x in lines] for part, lines in pack.pack["parts"].items()}
check("card shows the four parts", texts["summary"] == ["done: oiled", "now: trimming", "next: light at dusk"]
      and texts["decisions"] == ["waiting on Daniel: Beeswax or tallow? (a) Beeswax, b) Tallow)"]
      and texts["files"] == ["wick.py"] and texts["links"] == ["https://lanterns.example/wicks"], texts)
check("one row per line", len(pack.rows) == 6, list(pack.rows))
pack.part.set("decisions")
pack.entry.insert(0, "Use beeswax only")
pack.pin_typed()
root.update()
pinned = [r.line for r in pack.rows.values() if r.line["pinned"]]
check("a typed line is pinned", [x["text"] for x in pinned] == ["Use beeswax only"] and not pack.entry.get())
pack.part.set("files")
pack.entry.insert(0, "/etc/hosts")
pack.pin_typed()
check("an absolute path is refused", "Not pinned" in pack.error.cget("text") and pack.entry.get() == "/etc/hosts")
pack.entry.delete(0, "end")
link = next(r.line for r in pack.rows.values() if r.line["part"] == "links")
pack.unpin(link)
root.update()
check("unpin leaves a built line out", not pack.pack["parts"]["links"])
pack.edit(pinned[0])
row = pack.rows[pinned[0]["key"]]
row.entry.delete(0, "end")
row.entry.insert(0, "Beeswax, never tallow")
row.entry.focus_force()
root.update()
row.entry.event_generate("<Return>")
root.update()
check("edit rewrites a line", "Beeswax, never tallow" in [x["text"] for x in pack.pack["parts"]["decisions"]])
tiles = [w for w in panel.card_panel.chat_list.winfo_children() if isinstance(w, tk.Frame)]
check("chat tile marks it starts with the pack",
      any("starts with pack" in str(c.cget("text")) for t in tiles for c in t.winfo_children()
          if isinstance(c, tk.Label)))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])

script = install(work)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _name: str(script)))
save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
window = ChatWindow(root, directory=data, agents=[], config={}, offscreen=True, room_pane=RoomPane)
window.open(topic_id="west-keep")
pane = window._room
pane._ask_folder = lambda: str(project)
pane.pick_target("claude")
pane.pick_folder()
room = editor.chat_new(card["id"], "claude").card["chats"][-1]["room"]
window.open(topic_id=room)
for _ in range(3):
    window.refresh(force=True)
    root.update()
text = pane._term.get("1.0", "end")
check("new chat starts nothing", not popen_calls, popen_calls)
check("transcript opens with the pack", text.lstrip().startswith(context_packs.HEAD)
      and "Beeswax, never tallow" in text and text.index(context_packs.END) < text.index("[cli-avatars task"), text)
check("room pin carries the satchel", getattr(pane, "_pack_icon", None) is not None
      and pane._pack_icon.winfo_manager() == "pack")
window._entry.insert(0, "Trim the wicks please")
window._on_enter(SimpleNamespace())
deadline = time.time() + 15
while pane._runs and time.time() < deadline:
    root.update()
    time.sleep(0.02)
stdin = json.loads((project / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()[0])["stdin"]
check("one process, fixed argv, no shell", len(popen_calls) == 1 and not popen_calls[0][1].get("shell")
      and isinstance((popen_calls[0][0] or [popen_calls[0][1].get("args")])[0], list), popen_calls)
check("stdin: pack, then task, then prompt", stdin.index(context_packs.HEAD) < stdin.index("[cli-avatars task")
      < stdin.index("Trim the wicks please") and stdin.endswith("Trim the wicks please"), stdin)
check("pack cue played once", played.count("pack") == 1, played)
cli_runner.stop_all()
close_logging(data)
root.destroy()
print("done")
