"""Child process for ``test_room_card_dots``: the chat window's room cards draw their dots from the one palette.

    python tests/_room_card_dots_probe.py <repo root> <temp dir>

Prints ``ok <check>``; a failed check exits 1. Exit 77 when Tk has no display.
"""

import os
import sys
import time

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from chat_window import ChatWindow  # noqa: E402
from rooms import sample_agents  # noqa: E402
from status_palette import colour  # noqa: E402

window = ChatWindow(root, directory=sys.argv[2], agents=sample_agents(time.time()), config={}, offscreen=True)
window.open()
root.update()
shown, todo = [], [window._roster]
while todo:
    for child in todo.pop(0).winfo_children():
        todo.append(child)
        if isinstance(child, tk.Label) and child.cget("text").strip() == "●":
            shown.append(child.cget("fg").lower())
want = {colour(state).lower() for state in ("busy", "thinking", "subagent")}
root.destroy()
if not want <= set(shown):
    print(f"FAIL each state has its palette dot {sorted(want - set(shown))} missing in {shown}")
    raise SystemExit(1)
print("ok each state has its palette dot")
