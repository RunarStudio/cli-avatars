"""Child process for ``test_memory_desktop``: the Memory tab off-screen. Exit 77 when Tk has no display.

    python tests/_memory_probe.py <repo root>

Made-up notes in a temporary folder; the curator runs in-process with the fixture git (plumbing commit, no remote).
Prints ``ok <check>``.
"""

import os
import time
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
_TMP = tempfile.TemporaryDirectory()
BASE = Path(_TMP.name)
cfg = BASE / "gitconfig"
cfg.write_text("[user]\n\tname = Test Keeper\n\temail = keeper@example.invalid\n", encoding="utf-8")
os.environ.update(CLI_AVATARS_DATA_DIR=str(BASE / "data"), GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1",
                  HOME=str(BASE))
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
import test_memory as fixture  # noqa: E402
from cli_avatars.app import cues, memory_panel  # noqa: E402
from cli_avatars.app import memory_notes as mn  # noqa: E402
from cli_avatars.app import topic_rooms as tr  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out.extend(texts(child))
    return out


notes = BASE / "notes" / "memory"
data = BASE / "data"
data.mkdir()
played = []
cues.play = lambda _app, name: played.append(name)
focus.current = lambda _directory: None
app = SimpleNamespace(
    root=root, config={"memory": {"root": str(notes)}}, desktop_escape=True, _quit=noop, _toggle_rooms=noop,
    _toggle_chat=noop, _create_hud_win=noop, _rooms_shown=True, _chat_shown=False, _chat_directory=lambda: data,
    scanner=SimpleNamespace(get_agents=lambda: {}),
)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
root.deiconify()
root.geometry("1100x700")
root.update()

view.show_center("memory")
root.update()
panel = app._memory_panel
check("memory tab", view._center == "memory" and view._memory.winfo_ismapped())
check("missing root says so", "No notes folder" in panel.line.cget("text"))
create = next(w for w in panel.cards.winfo_children() if isinstance(w, tk.Button) and w.cget("text") == "Create")
create.invoke()
root.update()
check("create lays out", mn.exists(notes) and (notes / mn.CURATOR).is_file())
fixture.git(notes, "init", "-q")
fixture.commit(notes, "start")
(notes / "Topics" / "Garden").mkdir()
panel.refresh(force=True)

check("chat offers remember", memory_panel.offer("Stake the vines before the storm", "chat:garden@09:10", "tomatoes"))
root.update()
check("form filled", panel.text.get() == "Stake the vines before the storm" and panel.topic.get() == "tomatoes")
panel.kind.set("todo")
panel.category.set("Garden")
panel.save_button.invoke()
root.update()
check("inbox +1", mn.inbox_count(notes) == 1 and "inbox 1" in panel.line.cget("text"), panel.line.cget("text"))
check("remember cue", played == ["remember"], str(played))
check("app wrote only the inbox", not (notes / "Topics" / "Garden" / "tomatoes.md").exists())


def start(_python, _script, where):
    fixture.curator.run(where)
    return True


panel.watch(True)
with mock.patch.object(fixture.curator, "git", fixture.fixture_git(fixture.curator.git)), \
        mock.patch("chat_window.start_curator", start):
    panel.consolidate_button.invoke()
panel._at = 0
panel.watch(True)
root.update()
run = mn.status(notes)
check("consolidated", run.get("ok") and run.get("items") == 1 and mn.inbox_count(notes) == 0, str(run))
check("hash shown", run["commit"] and run["commit"] in panel.line.cget("text"), panel.line.cget("text"))
check("consolidated cue", played == ["remember", "consolidated"], str(played))
check("tree and next action", "   tomatoes" in texts(panel.tree)
      and "Next: Stake the vines before the storm" in texts(panel.cards), str(texts(panel.cards)))

topic = notes / "Topics" / "Garden" / "tomatoes.md"
topic.write_text(topic.read_text(encoding="utf-8").replace("updated:", "updated: 2001-01-01\nold:"), encoding="utf-8")
panel.refresh(force=True)
pin = next(w for w in texts(panel.cards) if w == "Pin room")
check("pin offered", bool(pin))
tr.set_pin(data / tr.PINS, "Garden/tomatoes", True)
rows = tr.shown_now(app, time.time())
check("pinned topic gets a room", rows == [("Garden/tomatoes", "tomatoes", "pinned")], str(rows))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
_TMP.cleanup()
