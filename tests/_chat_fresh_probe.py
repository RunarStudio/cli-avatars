"""Child process for ``test_chat_fresh``: the docked chat on a fresh install drives a fake Claude. Exit 77 without Tk.

    python tests/_chat_fresh_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. No real CLI, network or key.
"""

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

from chat_window import ChatWindow  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.room import save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from room_chat_fake import install  # noqa: E402

work = Path(sys.argv[2])
data = work / "data"
project = work / "demo-project"
project.mkdir(parents=True)
data.mkdir()


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


script = install(work)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _name: str(script)))
save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)

root.geometry("1100x600")
dock = tk.Frame(root, width=360, height=560)
dock.pack(side="right", fill="y")
dock.pack_propagate(False)
host = tk.Frame(dock)
host.pack(fill="both", expand=True)
window = ChatWindow(root, directory=data, agents=[], config={"files": {"dir": str(project)}}, container=host,
                    room_pane=RoomPane)
window.open()
root.update()
check("docked_entry_visible", window._entry.winfo_width() >= 120 and window._entry.winfo_ismapped(),
      window._entry.winfo_width())


def inside_dock(widget) -> bool:
    x, y = widget.winfo_rootx() - dock.winfo_rootx(), widget.winfo_rooty() - dock.winfo_rooty()
    return x >= 0 and y >= 0 and x + widget.winfo_width() <= dock.winfo_width() and \
        y + widget.winfo_height() <= dock.winfo_height()


pane = window._room
pane._ask_folder = lambda: str(project)
pane.pick_target("claude")
window._entry.insert(0, "Plan the bakery menu page")
window._on_enter(SimpleNamespace())
check("enter_without_topics_starts_a_run", bool(pane._runs), window._status.cget("text"))
deadline = time.time() + 15
while pane._runs and time.time() < deadline:
    root.update()
    window.refresh(force=True)
    time.sleep(0.02)
root.update()
for name in ("_folder_btn", "_mode_btn", "_new_btn", "_stop_btn"):
    check(f"docked{name}_inside_dock", inside_dock(getattr(pane, name)))
check("docked_entry_and_status_inside_dock", inside_dock(window._entry) and inside_dock(window._status))
text = pane._term.get("1.0", "end")
check("reply_shown", "Turn 1 reply" in text, text)
check("room_topic_listed", window._topic_id == pane.room_id and pane.target == "claude",
      (window._topic_id, pane.room_id, pane.target))

window.open(topic_id="garden-shop")
root.update()
check("avatar_topic_kept", window._topic_id == "garden-shop", window._topic_id)
root.destroy()
