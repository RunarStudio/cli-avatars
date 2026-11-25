"""Child process for ``test_update_bar``: the bar on the status bar and in Settings, off-screen. Exit 77 without Tk.

    python tests/_update_bar_probe.py <repo root>

A fake updater and made-up commits: no git, no PyInstaller, no helper. Prints ``ok <check>`` per check.
"""

import sys
import tempfile
from collections import deque
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
from cli_avatars.app import cues, update_ui  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update import progress  # noqa: E402
from cli_avatars.update.machine import PHASE_CURRENT, PHASE_FAILED, Toolchain, UpdateResult  # noqa: E402

OLD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


class Fake:
    """``run_update`` stand-in: says each line when the probe lets it, then decides."""

    def __init__(self, lines, result):
        self.lines, self.result, self.go, self.said = lines, result, threading.Semaphore(0), threading.Event()

    def __call__(self, **kw):
        for line in self.lines:
            self.go.acquire(timeout=5)
            kw["on_status"](line)
        self.go.acquire(timeout=5)
        return self.result


def pump(until, rounds=200) -> None:
    for _ in range(rounds):
        while pending:
            pending.popleft()()
        root.update()
        if until():
            return
        root.after(10)


tmp = tempfile.TemporaryDirectory()
data = Path(tmp.name) / "data"
install = Path(tmp.name) / "CLI Avatars"
data.mkdir()
install.mkdir()
played = []
cues.play = lambda _app, name: played.append(name)
update_ui.installed_dir = lambda: install
update_ui.app_data_dir = lambda: data
update_ui.spawn_detached = noop
pending = deque()
update_ui._later = lambda _app, fn: pending.append(fn)  # the worker hands lines to the Tk thread, as root.after does
held = [None]
focus.current = lambda _directory: held[0]

app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False,
)
view = DungeonWindow(app)
view.build(offscreen=True)
update_ui.mount_update_status(app)
root.deiconify()
root.geometry("1100x600")
update_ui.mount_update_settings(app, view._settings)
root.update()
update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))

bars = getattr(app, "_update_bars", {})
check("status bar has the bar", "status" in bars and bars["status"].widget.master is app._status_parent)
check("settings has the bar", "settings" in bars and bars["settings"].widget.winfo_exists())
check("hidden before a run", all(not b.widget.winfo_ismapped() for b in bars.values()))

phone = update_ui.PhoneUpdate(app)
fake = Fake(["Update: checking dev", "Update: pulling", "Update: selftest", "Update: building"],
            UpdateResult(PHASE_CURRENT, "Already on dev", OLD, OLD, None, (), None))
update_ui.run_update = fake
update_ui.start_update(app)
for _ in range(3):
    fake.go.release()
pump(lambda: app._update_line == "Update: selftest")
share = progress.step("Update: selftest")[0]
check("busy share", all(b.bar.pct == share and b.bar.tone == "busy" for b in bars.values())
      and bars["status"].widget.winfo_ismapped(), str([b.bar for b in bars.values()]))
fake.go.release()
pump(lambda: app._update_line == "Update: building")
check("shimmer while building", bars["status"].bar.shimmer and bars["settings"].bar.shimmer)
status = phone.status()
check("phone share", (status["pct"], status["tone"], status["shimmer"]) == (progress.step("Update: building")[0],
                                                                             "busy", True), str(status))
fake.go.release()
pump(lambda: not getattr(app, "_update_running", True))
bars = app._update_bars
check("full when up to date", all(b.bar.pct == 100 and b.bar.tone == "ok" for b in bars.values()),
      str([b.bar for b in bars.values()]))
check("ready cue once", played == ["ready"], str(played))

fake = Fake(["Update: checking dev", "Update: pulling"],
            UpdateResult(PHASE_FAILED, "git pull --ff-only failed", OLD, OLD, None, (), None))
update_ui.run_update = fake
update_ui.start_update(app)
for _ in range(3):
    fake.go.release()
pump(lambda: not getattr(app, "_update_running", True))
bars = app._update_bars
pulled = progress.step("Update: pulling")[0]
check("red with the reason", all(b.bar.tone == "bad" and b.bar.pct == pulled for b in bars.values())
      and "git pull --ff-only failed" in bars["settings"].bar.text
      and bars["settings"]._caption.cget("text") == "Stopped: git pull --ff-only failed",
      str([b.bar for b in bars.values()]))
status = phone.status()
check("phone failed", (status["tone"], status["pct"]) == ("bad", pulled), str(status))
held[0] = "a-task-in-focus"
fake = Fake([], UpdateResult(PHASE_CURRENT, "Already on dev", OLD, OLD, None, (), None))
update_ui.run_update = fake
update_ui.start_update(app)
fake.go.release()
pump(lambda: not getattr(app, "_update_running", True))
check("cue held in focus", played == ["ready"], str(played))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
tmp.cleanup()
