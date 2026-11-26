"""TIERS-SETTINGS.1 evidence: Settings › Chat › Chat tiers in the dock beside the Dungeon floor (throne room and two
topic rooms with their door chips). Main and Topic go to opus · medium; the sample lines and door chips follow. Then a
simulated Update on a made-up install pair: config.json before and after the swap.

Made-up rooms, names and cards (the ORCH.ROOM stage of ``shot_orch_rooms``) in a temporary data folder, removed
after; nothing starts a process. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_tier_settings.py <out-dir>
    python tools/shot_tier_settings.py --serve    # the phone's server, for tools/shot_phone_tier_settings.js

Writes tiers-settings.gif, desktop-1366.png, update-keeps.png.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
for _path in (_TOOLS, _TOOLS.parent / "tests"):
    sys.path.insert(0, str(_path))

import shot_orch_rooms as orch_shot  # noqa: E402
from shot_orch_rooms import caption  # noqa: E402
from shot_summon import cursor  # noqa: E402

orch_shot.W, orch_shot.H, orch_shot.DOCK = 1366, 768, 470
EVERY = 0.125
START = {"orchestrator": {"main": "claude"}, "text": {"size": 12}}


def film_rows(out: Path) -> None:
    import tkinter as tk

    from cli_avatars.app import orch_settings, tier_settings

    config_file = orch_shot._DATA / "config.json"
    config_file.write_text(json.dumps(START, indent=2), encoding="utf-8")
    orch_shot.load_sprites(orch_shot.REGISTRY)
    root = tk.Tk()
    root.geometry(f"{orch_shot.W}x{orch_shot.H}+0+0")
    stage = orch_shot.Stage(root)
    app = stage.app
    app.config, app._config_path = dict(START), config_file
    tk.Frame(stage.dock, bg="#0d0d1a", height=40).pack(fill="x")  # room for the caption
    app._orch_settings = orch_settings.mount(app, stage.dock)
    rows = tier_settings.mount(app, stage.dock)
    stage.tick(4.0)
    frames = []

    def film(seconds: float, text: str, widget=None) -> None:
        point = None
        if widget is not None:
            root.update()
            point = (widget.winfo_rootx() - root.winfo_rootx() + widget.winfo_width() // 2,
                     widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() // 2)
        for _ in range(max(1, round(seconds / EVERY))):
            stage.tick(EVERY, 0.025)
            shot = caption(stage.grab(), text)
            frames.append((cursor(shot, *point) if point else shot).convert("P", palette=1, colors=128))

    def pick(tier: str, model: str, effort: str) -> None:
        name = tier_settings.tiers.NAMES[tier]
        film(1.0, f"{name}: model box (Claude suggests fable, opus, sonnet, haiku)", rows[tier]["model"])
        rows[tier]["model"].set(model)
        rows[tier]["model"].event_generate("<<ComboboxSelected>>")
        film(1.0, f"{name}: {model}, saved at once", rows[tier]["effort"])
        rows[tier]["effort"].set(effort)
        rows[tier]["effort"].event_generate("<<ComboboxSelected>>")
        film(1.6, f"{name}: {effort} effort; the sample line and the door chip follow")

    film(2.0, "Settings › Chat › Chat tiers: each tier's model and effort (defaults: fable high for Main and Topic)")
    pick("main", "opus", "medium")
    pick("topic", "opus", "medium")
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    film(2.4, "config.json chat.tiers: " + json.dumps(saved["chat"]["tiers"]))
    stage.grab().save(out / "desktop-1366.png")
    film(1.0, "Reset to default puts a tier back on its default", rows["task"]["reset"])
    frames[0].save(out / "tiers-settings.gif", save_all=True, append_images=frames[1:],
                   duration=round(EVERY * 1000), loop=0, optimize=True)
    root.destroy()
    print("config", json.dumps(saved))


def update_keeps(out: Path) -> None:
    """A made-up install pair: the user's config.json, then a swap with a new build; before and after side by side."""
    from PIL import Image, ImageDraw, ImageFont

    from cli_avatars.app import tiers
    from cli_avatars.update.swap import apply_swap

    tmp = Path(tempfile.mkdtemp(prefix="tiers-update-"))
    try:
        install, staging = tmp / "CLI Avatars", tmp / "CLI Avatars.staging"
        for folder, exe in ((install, "old build"), (staging, "new build")):
            (folder / "_internal").mkdir(parents=True)
            (folder / "cli-avatars.exe").write_text(exe, encoding="utf-8")
        mine = tiers.with_tier(tiers.with_tier(START, "main", "opus", "medium"), "topic", "opus", "medium")
        (install / "_internal" / "config.json").write_text(json.dumps(mine, indent=2), encoding="utf-8")
        before = (install / "_internal" / "config.json").read_text(encoding="utf-8")
        outcome = apply_swap(install, staging, exe_name="cli-avatars.exe", bootcheck=lambda exe: 0,
                             relaunch=lambda exe: None, attempts=2, pause_s=0)
        after = (install / "_internal" / "config.json").read_text(encoding="utf-8")
        exe = (install / "cli-avatars.exe").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    font = ImageFont.load_default(size=15)
    image = Image.new("RGB", (1100, 560), (13, 13, 26))
    draw = ImageDraw.Draw(image)
    draw.text((24, 18), f"Simulated Update (apply_swap): {outcome}; the install folder now runs the {exe}",
              fill=(240, 230, 200), font=font)
    for left, title, body in ((24, "Before: CLI Avatars/_internal/config.json (old build)", before),
                              (560, "After: CLI Avatars/_internal/config.json (new build)", after)):
        draw.rectangle((left, 54, left + 516, 540), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
        draw.text((left + 12, 64), title, fill=(255, 207, 74), font=font)
        for i, line in enumerate(body.splitlines()):
            draw.text((left + 12, 96 + 20 * i), line, fill=(170, 204, 255), font=font)
    image.save(out / "update-keeps.png")
    print("update", outcome, "kept", json.loads(before) == json.loads(after))


def serve() -> None:
    """The phone's side: the ORCH.ROOM rooms with writes on; prints the pairing URL, serves till stdin closes."""
    from webui import auth, server, tier_routes

    orch_shot._seed(orch_shot.sr.SessionRooms(orch_shot._DATA / "ui" / "session_rooms.json"))
    config_file = orch_shot._DATA / "config.json"
    config_file.write_text(json.dumps(START, indent=2), encoding="utf-8")
    tier_routes.set_target(config_file, None)
    httpd = server.make_server(orch_shot._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(orch_shot._DATA)}", flush=True)
    sys.stdin.read()
    httpd.shutdown()
    httpd.server_close()


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--serve":
            serve()
        else:
            target = Path(sys.argv[1])
            target.mkdir(parents=True, exist_ok=True)
            film_rows(target)
            update_keeps(target)
    finally:
        shutil.rmtree(orch_shot._DATA, ignore_errors=True)
