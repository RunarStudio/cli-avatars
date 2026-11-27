"""Child process for ``test_bot_dots``: each bot row's dot in the Topics dock reads the one palette.

    python tests/_bot_dots_probe.py <repo root> <temp dir>

Prints ``ok <check>``; a failed check exits 1. Exit 77 when Tk has no display.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from bots.roster import Bot, Group  # noqa: E402
from bots.status import STATES, BotStatus  # noqa: E402
from cli_avatars.app import bots_ui, status_ink  # noqa: E402
from rooms import fade_hex  # noqa: E402

WANT = {
    "idle": status_ink.colour("idle"),
    "busy": status_ink.colour("busy"),
    "thinking": status_ink.colour("thinking"),
    "waiting_on_user": status_ink.colour("blocked"),
    "blocked": status_ink.colour("blocked"),
    "offline": fade_hex(status_ink.colour("idle")),
}
group = Group("g1", "Moon forge", False, 0)
rows = [(Bot(f"b{i}", f"Fern-{i}", "", "g1", "caine"), BotStatus(f"b{i}", state, "", "", 0.0))
        for i, state in enumerate(STATES)]
bots_ui.render_bot_sections(SimpleNamespace(bots=SimpleNamespace(sections=lambda: [(group, rows)])), root)
shown, todo = [], [root]
while todo:
    for child in todo.pop(0).winfo_children():
        todo.append(child)
        if isinstance(child, tk.Label) and child.cget("text") == "●":
            shown.append(child.cget("fg").lower())
want = [WANT[state].lower() for state in STATES]
root.destroy()
if shown != want:
    print(f"FAIL each state has its palette dot {shown} != {want}")
    raise SystemExit(1)
print("ok each state has its palette dot")
