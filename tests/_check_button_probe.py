"""Child process for ``test_check_updates``: Check for updates on the toolbar and in Settings, off-screen.

    python tests/_check_button_probe.py <repo root>

Prints ``ok <check>`` per check; any failed check exits 1. Exit 77 when Tk has no display.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import check_ui, update_ui  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update.check import PHASE_CURRENT, PHASE_NEWS, CheckResult  # noqa: E402
from cli_avatars.update.machine import Toolchain  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


tmp = tempfile.TemporaryDirectory()
data = Path(tmp.name)
update_ui.app_data_dir = check_ui.app_data_dir = lambda: data
app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False,
)
view = DungeonWindow(app)
view.build(offscreen=True)
update_ui.mount_update_status(app)
update_ui.mount_update_settings(app, view._settings)
root.deiconify()
root.geometry("1366x700")
view._settings.pack(fill="both", expand=True)
root.update()

button, update = app._check_tool, app._update_tool
siblings = button.master.pack_slaves()
check("beside update in window group", button.master is update.master
      and siblings.index(button) == siblings.index(update) + 1, str(siblings))
check("checking at start", button.cget("state") == "disabled" and button._kit_reason.startswith("Checking git"))

update_ui.apply_probe(app, Toolchain(None, ("python",), True, "git is not on PATH"))
check("missing git", button.cget("state") == "disabled" and button._kit_reason == "git is not on PATH")

update_ui.installed_dir = lambda: None
update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))
check("from source enabled", button.cget("state") == "normal" and update.cget("state") == "disabled")

calls = []
real_start = check_ui.start_check
check_ui.start_check = calls.append
button.invoke()
check("click calls start_check", calls == [app], str(calls))
check_ui.start_check = real_start

settings = [w for w in app._update_panel.winfo_children()]
row = app._update_button.master
texts = [w.cget("text") for w in row.winfo_children() if isinstance(w, tk.Button)]
check("settings check beside update app", texts == ["Update app", "Check for updates"], str(texts))

check_ui._finish(app, CheckResult(PHASE_NEWS, "3 new on dev", 3, ("Map scroll unrolls", "Quieter torches", "Ember")))
root.update()
badge = getattr(update, "_check_badge", None)
check("ember badge on update", badge is not None and badge.winfo_ismapped() and badge.cget("text") == "3",
      badge and badge.cget("text"))
sbadge = getattr(app._update_button, "_check_badge", None)
check("badge on update app", sbadge is not None and sbadge.winfo_ismapped() and sbadge.cget("text") == "3")
shown = " ".join(str(w.cget("text")) for w in app._update_panel.winfo_children() if isinstance(w, tk.Label))
check("settings lists subjects", "3 new on dev" in shown and "Map scroll unrolls" in shown, shown)
check("status line", app._update_label.cget("text").startswith("Check: 3 new on dev"), app._update_label.cget("text"))

check_ui._finish(app, CheckResult(PHASE_CURRENT, "Up to date"))
root.update()
check("badge gone when up to date", not update._check_badge.winfo_ismapped())
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
tmp.cleanup()
