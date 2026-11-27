"""Child process for ``test_card_follow``: an agent's edits to the open card's title, notes and progress show in
the card at once, in place, while text Daniel is still typing stays. Made-up data; exit 77 without Tk.

    python tests/_card_follow_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.tasks_panel import TasksPanel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def widgets(widget) -> list:
    return [str(widget)] + [name for child in widget.winfo_children() for name in widgets(child)]


data = Path(sys.argv[2])
set_topic(data, "forge", title="Forge", project="forge", status="open")
registry = Registry(data)
card = registry.task_create("forge", "Relight the forge", topic="forge")["id"]
root.geometry("1100x600")
host = tk.Frame(root)
host.pack(fill="both", expand=True)
panel = TasksPanel(host, lambda: data, lambda: "forge")
panel.refresh(force=True)
panel.open_card(card)
root.update()
sheet, open_ = widgets(panel.card_panel.sheet), panel.card_panel

registry.task_edit(card, title="Relight the big forge", body="Coal first, then bellows.")
registry.task_progress(card, 40, "half the coal in")
panel.refresh(force=True)
root.update()
check("agent_title_in_the_header", open_.head_title.cget("text") == "Relight the big forge", open_.head_title.cget("text"))
check("agent_title_in_the_field", open_.title.get() == "Relight the big forge", open_.title.get())
check("agent_notes_in_the_field", open_.body.get("1.0", "end-1c") == "Coal first, then bellows.",
      open_.body.get("1.0", "end-1c"))
check("agent_progress_in_the_field", open_.progress.get() == "40", open_.progress.get())
check("agent_note_in_the_field", open_.note.get() == "half the coal in", open_.note.get())
check("agent_edit_keeps_the_open_card", widgets(open_.sheet) == sheet)

open_.title.insert("end", " today")
registry.task_progress(card, 60, "bellows on")
panel.refresh(force=True)
root.update()
check("typed_title_stays", open_.title.get() == "Relight the big forge today", open_.title.get())
check("agent_progress_moves_on", open_.progress.get() == "60", open_.progress.get())
open_._save()
root.update()
check("typed_title_saves", registry.task_get(card)["title"] == "Relight the big forge today")
check("saved_title_in_the_header", open_.head_title.cget("text") == "Relight the big forge today")
root.destroy()
print("done")
