"""Child process for ``test_installday``: editing a task's title or body keeps every widget, so nothing blinks.

    python tests/_task_edit_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1; exit 77 when Tk has no display.
"""

import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.bootcheck import check_task_edit  # noqa: E402
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
registry.task_create("forge", "Sweep the hall", topic="forge")
root.geometry("1100x600")
host = tk.Frame(root)
host.pack(fill="both", expand=True)
panel = TasksPanel(host, lambda: data, lambda: "forge")
panel.refresh(force=True)
root.update()
panel.open_card(card)
root.update()
board, sheet = widgets(panel._grid), widgets(panel.card_panel.sheet)
tile = panel.cards[card]

panel.card_panel.title.delete(0, "end")
panel.card_panel.title.insert(0, "Relight the big forge")
panel.card_panel._save()
root.update()
check("title_edit_keeps_the_tile", panel.cards[card] is tile)
check("title_shows_in_place", tile.parts["title"].cget("text") == "Relight the big forge", tile.parts["title"])
check("title_edit_keeps_the_card_list", widgets(panel._grid) == board)
check("title_edit_keeps_the_open_card", widgets(panel.card_panel.sheet) == sheet,
      (sorted(set(sheet) - set(widgets(panel.card_panel.sheet))), sorted(set(widgets(panel.card_panel.sheet)) - set(sheet))))

panel.card_panel.body.insert("end", "Bring the coal first.")
panel.card_panel._save()
root.update()
check("body_edit_keeps_the_card_list", widgets(panel._grid) == board)
check("body_edit_keeps_the_open_card", widgets(panel.card_panel.sheet) == sheet)
check("body_saved", registry.task_get(card)["body"] == "Bring the coal first.")
check("boot_check_passes", check_task_edit()[0] == "ok", check_task_edit())
root.destroy()
