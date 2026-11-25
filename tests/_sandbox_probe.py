"""Child process for ``test_sandbox``: Try it risky on a card, its room on the map, Bin and Promote. Exit 77 without Tk.

    python tests/_sandbox_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. The git repo is a fixture made here; no CLI starts.
"""

import subprocess  # noqa: TID251  # wraps Popen to see every process
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

import sandbox  # noqa: E402
from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.session_rooms import model_for  # noqa: E402
from cli_avatars.app.tasks_edit import TaskEditor  # noqa: E402
from cli_avatars.model.room import set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import close_logging  # noqa: E402
from test_sandbox import make_repo  # noqa: E402
from topics import set_topic  # noqa: E402

work = Path(sys.argv[2])
data = work / "data"
data.mkdir(parents=True)
repo = make_repo(work)


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


popen_calls, played, opened = [], [], []
real_popen = subprocess.Popen


def counting_popen(*args, **kwargs):
    popen_calls.append(args[0] if args else kwargs.get("args"))
    return real_popen(*args, **kwargs)


subprocess.Popen = counting_popen
cues.play = lambda app, name: played.append(name)
set_topic(data, "west-keep", title="West keep", project="keep-demo", status="open")
set_working_dir(data, "west-keep", str(repo), check=cli_runner.validate_working_dir)
editor = TaskEditor(data, "west-keep")
first = editor.create("Wild wick idea").card
second = editor.create("Brass lantern idea").card

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
panel.open_card(first["id"])
root.update()
card_panel = panel.card_panel
card_panel._open_chat = lambda room, new: opened.append((room, new))
section = card_panel.sandbox
check("card offers try it risky", section is not None and section.try_button.winfo_manager() == "pack")
section.try_button.invoke()
root.update()
box = sandbox.for_card(data, first["id"])
check("try it risky opens its chat", box is not None and opened == [(box["room"], True)], opened)
check("risky cue", played == ["risky"], played)
model = model_for(app)
rooms = [r for r in model.layout(time.time())["rooms"] if r.get("kind") == "sandbox"]
check("room on the map", [r["sandbox"] for r in rooms] == [box["id"]], rooms)
check("branch shown on the card", box["branch"] in section.branch.get())

(Path(box["path"]) / "flame.py").write_text("x = 1\n", encoding="utf-8")
section.bin_button.invoke()
root.update()
check("bin asks when dirty", "uncommitted" in section.message.cget("text").lower()
      and section.confirm_button.winfo_manager() == "pack" and Path(box["path"]).exists())
section.confirm_button.invoke()
root.update()
check("bin with confirm", sandbox.for_card(data, first["id"])["state"] == sandbox.BINNED
      and not Path(box["path"]).exists())
check("trapdoor cue", played[-1] == "trapdoor", played)
check("try again offered", section.try_button.winfo_manager() == "pack")

panel.open_card(second["id"])
root.update()
section = card_panel.sandbox
section.try_button.invoke()
root.update()
box = sandbox.for_card(data, second["id"])
section.promote_button.invoke()
root.update()
check("promote shows the branch", sandbox.for_card(data, second["id"])["state"] == sandbox.PROMOTED
      and section.branch.get() == box["branch"] and "promoted" in section.message.cget("text").lower())
check("seal cue", played[-1] == "seal", played)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
check("no cli started", popen_calls and all(argv[0] == "git" for argv in popen_calls), popen_calls)
close_logging(data)
root.destroy()
print("done")
