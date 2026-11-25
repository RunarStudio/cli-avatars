"""UPDATE-BAR.1 evidence: a made-up update run through its phases in the Dungeon window, under Xvfb.

A fake updater says each phase in turn: no git, no PyInstaller, no helper. The data and install folders are
fresh temp dirs, removed after.

    xvfb-run -a python tools/shot_update_bar.py <out-dir>

Writes ``update-bar.gif``: Settings and the status bar blown up 2x, one frame per 100 ms.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="update-bar-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_TMP / "data")

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from cli_avatars.app import cues, update_ui  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update.machine import PHASE_CURRENT, PHASE_FAILED, Toolchain, UpdateResult  # noqa: E402
from cli_avatars.update.version import STAMP_NAME, write_stamp  # noqa: E402

W, H = 1366, 768
OLD, NEW = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678", "f00dfacec0ffee1234567890abcdef1234567890"
RUN = (("Update: checking dev", 1.6), ("Update: pulling", 0.8), ("Update: selftest", 0.9), ("Update: boot check", 0.8),
       ("Update: building", 2.2))


class Fake:
    """``run_update`` stand-in: each line when the shot says so, then the result."""

    def __init__(self, lines, result):
        self.lines, self.result, self.go = lines, result, threading.Semaphore(0)

    def __call__(self, **kw):
        for line in self.lines:
            self.go.acquire(timeout=30)
            kw["on_status"](line)
        self.go.acquire(timeout=30)
        return self.result


def noop(*_args, **_kwargs) -> None:
    return None


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    install = _TMP / "CLI Avatars"
    install.mkdir(parents=True)
    (_TMP / "data").mkdir()
    write_stamp(install / STAMP_NAME, "1.4.0", OLD)
    pending = deque()
    update_ui.installed_dir = lambda: install
    update_ui.spawn_detached = noop
    update_ui._later = lambda _app, fn: pending.append(fn)
    cues.play = noop
    root = tk.Tk()
    root.geometry(f"{W}x{H}+0+0")
    app = SimpleNamespace(root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop,
                          _toggle_chat=noop, _create_hud_win=noop, _rooms_shown=True, _chat_shown=False)
    app._build_config_ui = lambda win: update_ui.mount_update_settings(app, win)
    view = DungeonWindow(app)
    view.build(offscreen=True)
    update_ui.mount_update_status(app)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    view.set_right(True, "settings")
    update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))
    frames: list[Image.Image] = []

    def film(seconds: float, text: str) -> None:
        for _ in range(round(seconds / 0.1)):
            while pending:
                pending.popleft()()
            root.update()
            root.after(100)
            frames.append(_frame(root, text))

    film(0.8, "Settings: Update app. The bar waits until an update starts")
    fake = Fake([line for line, _s in RUN], UpdateResult(PHASE_CURRENT, "Already on dev", OLD, NEW, None, (), None))
    update_ui.run_update = fake
    update_ui.start_update(app)
    for line, seconds in RUN:
        fake.go.release()
        glint = " (glints: no measurable progress)" if line.endswith(("dev", "building")) else ""
        step = line.removeprefix("Update: ")
        film(seconds, step[0].upper() + step[1:] + glint)
    fake.go.release()
    film(1.6, "Up to date: the bar fills and gilds; a soft ready cue")
    fake = Fake(["Update: checking dev", "Update: pulling"],
                UpdateResult(PHASE_FAILED, "git pull --ff-only failed", OLD, NEW, None, (), None))
    update_ui.run_update = fake
    update_ui.start_update(app)
    for seconds in (0.8, 0.8, 0.1):
        fake.go.release()
        film(seconds, "A second run that fails at the pull")
    film(1.8, "Failed: the bar turns red where it stopped, with the reason")
    frames[0].save(out / "update-bar.gif", save_all=True, append_images=frames[1:], duration=100, loop=0,
                   optimize=True)
    root.destroy()


def _frame(root, text: str) -> Image.Image:
    x, y = root.winfo_rootx(), root.winfo_rooty()
    shot = ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))
    dock = shot.crop((W - 360, 56, W, 190)).resize((720, 268), Image.NEAREST)
    status = shot.crop((0, H - 26, 520, H)).resize((1040, 52), Image.NEAREST)
    frame = Image.new("RGB", (1040, 380), (12, 10, 16))
    frame.paste(dock, (0, 40))
    frame.paste(status, (0, 324))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 1040, 34), fill=(23, 16, 34))
    draw.line((0, 34, 1040, 34), fill=(224, 170, 62), width=2)
    draw.text((12, 11), text, fill=(240, 230, 200))
    draw.text((736, 120), "Settings dock (2x)", fill=(154, 152, 184))
    draw.text((736, 298), "Status bar (2x)", fill=(154, 152, 184))
    return frame


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
