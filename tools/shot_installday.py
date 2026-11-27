"""INSTALLDAY evidence: a fresh install opening on the Throne Room with the starter cards, the setup card's save
folder and bot bridge steps, the default skins and the whole window at 1366 px.

The real app starts in-process on a temporary HOME, data folder and config.json (removed after); PATH holds stub
``claude`` and ``grok`` files that never run. Demo avatars only. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_installday.py <out-dir>
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="installday-"))
for name in ("home", "data", "bin"):
    (_TMP / name).mkdir()
os.environ.update(HOME=str(_TMP / "home"), USERPROFILE=str(_TMP / "home"), CLI_AVATARS_DATA_DIR=str(_TMP / "data"))
os.environ["PATH"] = str(_TMP / "bin") + os.pathsep + os.environ.get("PATH", "")
for cli in ("claude", "grok"):
    stub = _TMP / "bin" / cli
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
W, H = 1366, 768


def grab():
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=(0, 0, W, H), xdisplay=os.environ.get("DISPLAY")).convert("RGB")


def skins(out: Path) -> None:
    """Caine (main orchestrator), Michimaru (Claude), amongo at 70 % (Grok bot) on one floor, 3x."""
    from PIL import Image, ImageDraw

    from cli_avatars.app import av_roster as ar

    rows = (("Caine: main orchestrator", ar.LOOKS[ar.ORCHESTRATOR], "caine.png", 48, 48, 0),
            ("Michimaru: Claude", ar.LOOKS[ar.CLAUDE], "Michimaru.png", 40, 51, 0),
            ("amongo 70 %: Grok bot", ar.LOOKS[ar.GROK], "amongo.png", 40, 40, 0),
            ("amongo before (100 %)", ar.replace(ar.LOOKS[ar.GROK], shrink=1.0), "amongo.png", 40, 40, 0))
    scale, gap = 3, 40
    canvas = Image.new("RGB", (len(rows) * (48 * scale + gap) + gap, 48 * scale + 90), (13, 13, 26))
    draw = ImageDraw.Draw(canvas)
    floor = 30 + 48 * scale
    draw.rectangle((0, floor, canvas.width, floor + 4), fill=(122, 31, 61))
    x = gap
    for text, look, fname, fw, fh, col in rows:
        sheet = Image.open(ROOT / "Sprites" / fname).convert("RGBA")
        frame = ar.roster_frame(sheet.crop((col * fw, 0, col * fw + fw, fh)), look, scale, False)
        canvas.paste(frame, (x, floor - frame.height), frame)
        draw.text((x, floor + 14), text, fill=(240, 230, 200))
        x += 48 * scale + gap
    canvas.save(out / "skins.png")


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    from cli_avatars.app import main as app_main
    from cli_avatars.app import shell

    shell.CONFIG_PATH = _TMP / "config.json"
    frames: list = []
    real_run = shell.OverlayApp.run

    def run(app) -> None:
        root = app.root
        root.after(200, lambda: root.geometry(f"{W}x{H}+0+0"))

        def frame() -> None:
            frames.append(grab().resize((W * 3 // 4, H * 3 // 4)))

        for i in range(24):
            root.after(400 + i * 350, frame)

        def desktop() -> None:
            grab().save(out / "desktop-1366.png")
            from cli_avatars.app import start_card

            start_card.reopen(app)

        def tested() -> None:
            from cli_avatars.app import start_card

            found = start_card.card(app)
            if found is not None:
                found.test_bridge()

        def bridge() -> None:
            grab().save(out / "setup-bridge.png")
            app.root.destroy()

        root.after(9500, desktop)
        root.after(11500, tested)
        root.after(12500, bridge)
        real_run(app)

    shell.OverlayApp.run = run
    try:
        app_main.main([])
    except SystemExit:
        pass
    if frames:
        frames[0].save(out / "first-run.gif", save_all=True, append_images=frames[1:], duration=350, loop=0,
                       optimize=True)
    skins(out)
    notes = (_TMP / "data" / "ui" / "first_run.json")
    print(notes.read_text(encoding="utf-8") if notes.is_file() else "no first-run notes")
    return 0


if __name__ == "__main__":
    try:
        code = main(Path(sys.argv[1]))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    raise SystemExit(code)
