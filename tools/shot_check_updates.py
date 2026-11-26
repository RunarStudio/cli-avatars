"""CHECK-UPD.1 evidence: Check for updates against a made-up repo, in the Dungeon window under Xvfb.

Real git on a fixture: ``lantern-works`` with a local origin in a fresh temp dir (no network, no real clone). The
first check says Up to date; then dev moves three commits and the second check says 3 new on dev with the subjects
and an ember badge on Update. Nothing is pulled or built. The temp dirs are removed after.

    xvfb-run -a python tools/shot_check_updates.py <out-dir>

Writes ``check-updates.gif`` (toolbar, Settings and status bar blown up 2x) and ``desktop-1366.png``.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: TID251  # fixture repo only, fixed argv
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="check-updates-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_TMP / "data")

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from cli_avatars.app import check_ui, cues, update_ui  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.update.machine import Toolchain  # noqa: E402
from cli_avatars.update.proc import run_fixed  # noqa: E402
from cli_avatars.update.version import STAMP_NAME, write_stamp  # noqa: E402

W, H = 1366, 768
GIT = shutil.which("git") or "git"
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="Wren Example", GIT_AUTHOR_EMAIL="wren@example.invalid",
           GIT_COMMITTER_NAME="Wren Example", GIT_COMMITTER_EMAIL="wren@example.invalid")
NEWS = ("Ember badge on the Update button", "Quieter torches in the hall", "Map scroll unrolls from the left")


def git(*args, cwd) -> str:
    done = subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, env=ENV, timeout=30, shell=False,
                          check=True)
    return done.stdout.strip()


def commit(origin: Path, subject: str) -> None:
    """A commit on the fixture origin's dev by plumbing."""
    (origin / "notes.txt").write_text(subject + "\n", encoding="utf-8")
    git("add", "notes.txt", cwd=origin)
    parent = subprocess.run([GIT, "rev-parse", "--verify", "--quiet", "HEAD"], cwd=origin, capture_output=True,
                            text=True, env=ENV, timeout=30, shell=False).stdout.strip()
    sha = git("commit-tree", git("write-tree", cwd=origin), "-m", subject, *(["-p", parent] if parent else []),
              cwd=origin)
    git("update-ref", "HEAD", sha, cwd=origin)


def noop(*_args, **_kwargs) -> None:
    return None


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    origin, src, install = _TMP / "lantern-works", _TMP / "src", _TMP / "CLI Avatars"
    (_TMP / "data").mkdir()
    install.mkdir()
    git("init", "-q", "-b", "dev", str(origin), cwd=_TMP)
    commit(origin, "Lantern room gets a door")
    git("clone", "-q", "--branch", "dev", str(origin), str(src), cwd=_TMP)
    write_stamp(install / STAMP_NAME, "1.4.0", git("rev-parse", "HEAD", cwd=src))

    def slow(argv, **kw):
        if "fetch" in argv:
            time.sleep(1.4)  # the fixture fetch is instant; slowed so the glint shows
        return run_fixed(argv, **kw)

    real = check_ui.check_dev
    check_ui.check_dev = lambda **kw: real(**{**kw, "install_dir": None, "source_root": src, "runner": slow})
    update_ui.installed_dir = lambda: install
    pending = deque()
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
    update_ui.apply_probe(app, Toolchain(GIT, ("python",), True, ""))
    frames: list[Image.Image] = []

    def film(seconds: float, text: str, until=None) -> None:
        end = time.time() + seconds
        while time.time() < end or (until is not None and not until()):
            while pending:
                pending.popleft()()
            root.update()
            root.after(100)
            frames.append(_frame(root, app, view, text))

    def checked() -> bool:
        return not getattr(app, "_check_running", False)

    film(1.2, "Made-up repo lantern-works. Settings: Update app and Check for updates")
    app._check_tool.invoke()
    film(0.6, "Check for updates: fetches dev only (the bar glints in its fetch phase)", checked)
    film(2.2, "Up to date: nothing is pulled, built or restarted")
    for subject in NEWS:
        commit(origin, subject)
    film(1.4, "dev moves: three new commits land on the made-up origin")
    app._check_tool.invoke()
    film(0.6, "Check again", checked)
    film(3.4, "3 new on dev: the newest subjects, and an ember badge on Update")
    frames[0].save(out / "check-updates.gif", save_all=True, append_images=frames[1:], duration=100, loop=0,
                   optimize=True)
    _grab(root).save(out / "desktop-1366.png")
    root.destroy()


def _grab(root) -> Image.Image:
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))


def _box(widget, root, pad: int = 0) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    return x - pad, y - pad, x + widget.winfo_width() + pad, y + widget.winfo_height() + pad


def _frame(root, app, view, text: str) -> Image.Image:
    shot = _grab(root)
    tools = shot.crop(_box(app._update_tool.master, root, 4))
    tools = tools.resize((tools.width * 2, tools.height * 2), Image.NEAREST)
    x0, y0, x1, _y1 = _box(view._settings, root)
    dock = shot.crop((x0, y0, x1, y0 + 230)).resize(((x1 - x0) * 2, 460), Image.NEAREST)
    status = shot.crop((0, H - 26, 520, H)).resize((1040, 52), Image.NEAREST)
    width = max(1040, dock.width + 200, tools.width + 220)
    frame = Image.new("RGB", (width, 46 + tools.height + 12 + dock.height + 12 + status.height + 8), (12, 10, 16))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, width, 34), fill=(23, 16, 34))
    draw.line((0, 34, width, 34), fill=(224, 170, 62), width=2)
    draw.text((12, 11), text, fill=(240, 230, 200))
    y = 46
    frame.paste(tools, (0, y))
    draw.text((tools.width + 16, y + 8), "Toolbar, WINDOW group (2x)", fill=(154, 152, 184))
    y += tools.height + 12
    frame.paste(dock, (0, y))
    draw.text((dock.width + 16, y + 8), "Settings dock (2x)", fill=(154, 152, 184))
    y += dock.height + 12
    frame.paste(status, (0, y))
    return frame


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
