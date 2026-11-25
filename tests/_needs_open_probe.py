"""Child process for ``test_needs_you_desktop``: a card opened from Needs you shows with no board topic.

    python tests/_needs_open_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1; exit 77 when Tk has no display.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import needs_panel  # noqa: E402
from cli_avatars.app.tasks_panel import TasksPanel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


data = Path(sys.argv[2])
set_topic(data, "forge", title="Forge", project="forge", status="open")
card = Registry(data).task_create("forge", "Relight the forge", topic="forge")["id"]
root.geometry("1100x600")
host = tk.Frame(root)
host.pack(fill="both", expand=True)
panel = TasksPanel(host, lambda: data, lambda: "")
panel.refresh(force=True)
root.update()
check("empty board", panel.empty.winfo_ismapped())
app = SimpleNamespace(dungeon=SimpleNamespace(show_center=lambda _name: None), _tasks_panel=panel)
needs_panel.open_item(app, {"card": card})
root.update()
panel.refresh(force=True)
root.update()
check("card shown", panel.card_panel.frame.winfo_ismapped(), str(panel.board and panel.board.topic))
check("same card", panel.card_panel.card is not None and panel.card_panel.card["id"] == card)
