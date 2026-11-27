"""Child process for ``test_installday``: Send with no folder and no confirmed binary. Exit 77 without Tk.

    python tests/_installday_send_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1. No CLI starts: ``prepare`` only builds the request.
"""

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter  # noqa: F401
except Exception:
    raise SystemExit(77)

from chat_window import room_tools  # noqa: E402
from cli_avatars.app.room_pane import RoomPane  # noqa: E402
from cli_avatars.model.room import load_binary_pin, load_room, save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402

work = Path(sys.argv[2])
data = work / "data"
data.mkdir(parents=True, exist_ok=True)
bin_dir = work / "bin"
bin_dir.mkdir()
stub = bin_dir / ("claude.exe" if sys.platform == "win32" else "claude")
stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
said = []


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def pane(room: str, config: dict) -> RoomPane:
    window = SimpleNamespace(directory=lambda: data, _config=lambda: config)
    made = RoomPane(window, room_tools())
    made.room_id, made.target = room, "claude"
    made._write = made._show = made._paint = lambda *a, **k: None
    made._status = said.append
    made._ask_folder = lambda: (_ for _ in ()).throw(AssertionError("the folder dialog opened on Send"))
    return made


os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
vault = work / "Notes vault ñ"
request = pane("demo", {"files": {"dir": str(vault)}}).prepare("hello")
check("send_pins_a_binary_found_on_path", request is not None and load_binary_pin(data, "claude") is not None
      and Path(load_binary_pin(data, "claude")["path"]).resolve() == stub.resolve(), said)
check("send_with_no_folder_uses_the_save_folder", Path(request.working_dir) == vault.resolve()
      and Path(load_room(data, "demo").working_dir) == vault.resolve(), said)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(stub)))
save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
request = pane("other", {"files": {"dir": str(work / "file")}}).prepare("hi") if (work / "file").write_text("x") else None
check("a_save_folder_that_cannot_be_made_says_why", request is None and any("Could not create" in s for s in said), said)
print("done")
