"""Child process for ``test_update_button``: the toolbar Update button off-screen. Exit 77 when Tk has no display.

    python tests/_update_button_probe.py <repo root>

Prints ``ok <check>`` per check; any failed check exits 1.
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

from cli_avatars.app import update_ui  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update.machine import Toolchain  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False,
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1100x600")
root.update()

button = app._update_tool
check("in window group", button.master is view._pin.master and button.cget("text") == "Update")
check("checking at start", button.cget("state") == "disabled" and button._kit_reason == "Checking git and PyInstaller")

update_ui.apply_probe(app, Toolchain(None, (), False, "git is not on PATH"))
check("missing tool", button.cget("state") == "disabled" and button._kit_reason == "git is not on PATH")

update_ui.installed_dir = lambda: None
update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))
check("from source", button.cget("state") == "disabled" and button._kit_reason.startswith("Running from source"))

button.event_generate("<Enter>")
root.after(500, root.quit)
root.mainloop()
tip = getattr(root, "_toolbar_tip", None)
check("reason as tooltip", tip is not None and tip.cget("text") == button._kit_reason, tip and tip.cget("text"))
button.event_generate("<Leave>")

update_ui.installed_dir = lambda: Path("installed")
update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))
check("enabled", button.cget("state") == "normal" and button._kit_reason == "")

calls = []
update_ui.start_update = calls.append
button.invoke()
check("click calls start_update", calls == [app], str(calls))

app._update_running = True
update_ui.sync_update_tool(app)
check("running", button.cget("state") == "disabled" and "already running" in button._kit_reason)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
