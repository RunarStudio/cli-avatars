"""Child process for ``test_local_time``: Settings › Update's "Last checked" line in local time. Exit 77 without Tk.

    python tests/_local_time_probe.py <repo root> <data dir>

Run with ``TZ=Europe/Madrid``; the stored stamp stays UTC. Prints ``ok <check>`` or ``FAIL <check>``.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import update_ui  # noqa: E402

(Path(sys.argv[2]) / "update_state.json").write_text(json.dumps({"last_checked": "2026-11-27T10:05:00Z"}),
                                                     encoding="utf-8")
frame = tk.Frame(root)
update_ui._fill(SimpleNamespace(_update_panel=frame, _update_block=""))
texts = [str(w.cget("text")) for w in frame.winfo_children() if isinstance(w, tk.Label)]
ok = any("Last checked  2026-11-27 11:05" in t for t in texts)
print(f"{'ok' if ok else 'FAIL'} update last checked in local time {texts if not ok else ''}")
root.destroy()
raise SystemExit(0 if ok else 1)
