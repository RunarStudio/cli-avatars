"""FONT.1 evidence: the real Dungeon window in each text face, switched live, plus a standup bubble and a door sign.

Made-up topics, avatars and chat lines (the START-SETUP stage of ``shot_start_setup``) in a temporary data folder,
removed after; no CLI starts. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_fonts.py <out-dir>

Writes ``fonts.png`` (panel, bubble and sign in all four choices, labelled), ``before-after.png`` (Pixel vs
Atkinson Hyperlegible, same view), ``desktop-1366.png`` and ``settings.png`` (the Text font rows).
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools"))

import shot_start_setup as stage  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import text_fonts as fonts  # noqa: E402

CROP = (666, 0, 1366, 768)
LINES = (("user", "Can the goblin boss move task 12 to Done before the moon rises?"),
         ("claude:room", "Moved task 12 to Done. Ill 1 O0 bdpq all read clearly; the gate hinges are oiled."),
         ("user", "Good. Next: paint the west gate, then light the torches in the hall."))
STAND = ("Ash", "done: hinges oiled · next: paint the west gate · stuck: waiting on the shears")


def seed_chat() -> None:
    from events import append_channel

    for n, (sender, note) in enumerate(LINES):
        append_channel(stage._DATA, {"ts": time.time() - 300 + n * 60, "from": sender, "channel": "west-keep",
                                     "to": "user" if sender != "user" else "claude:room", "icon": "speech",
                                     "note": note, "kind": "msg"})


def label(image: Image.Image, text: str, picked: fonts.Choice) -> Image.Image:
    """``text`` over ``image`` on a dark band, written in the face it names (Pixel in the old monospace)."""
    face = fonts.pil_font(22, True, picked) or fonts.pil_font(22, True, fonts.Choice())
    out = Image.new("RGB", (image.width, image.height + 44), (12, 10, 16))
    out.paste(image, (0, 44))
    ImageDraw.Draw(out).text((14, 9), text, fill=(255, 210, 122), font=face)
    return out


def art(picked: fonts.Choice) -> Image.Image:
    from cli_avatars.app import standup_art
    from cli_avatars.app.door_signs import sign_image

    with fonts.using(picked):
        bubble = standup_art.bubble(*STAND, "stuck", "", 2)
        sign = sign_image(("West keep", "Doing: paint the west gate", "Waiting on the shears"), True, None, 2)
    out = Image.new("RGBA", (CROP[2] - CROP[0], bubble.height + sign.height + 48), (20, 16, 24, 255))
    out.alpha_composite(bubble, ((out.width - bubble.width) // 2, 16))
    out.alpha_composite(sign, ((out.width - sign.width) // 2, bubble.height + 32))
    return out.convert("RGB")


def main(out: Path) -> None:
    import tkinter as tk

    out.mkdir(parents=True, exist_ok=True)
    stage.seed_topics()
    seed_chat()
    root = tk.Tk()
    host = stage.build(root)
    host._status_parent.pack(side="bottom", fill="x", before=root.winfo_children()[0])
    film = stage.Film(root)
    shots = {}
    for key in fonts.CHOICES:
        picked = fonts.Choice(key)
        fonts.apply(root, picked)
        for _ in range(3):
            root.update()
            time.sleep(0.1)
        full = film.grab()
        shots[key] = full
        if key == "atkinson":
            full.save(out / "desktop-1366.png")
    columns = []
    for key in fonts.CHOICES:
        picked = fonts.Choice(key)
        panel = shots[key].crop(CROP).convert("RGB")
        tile = Image.new("RGB", (panel.width, panel.height + 400), (20, 16, 24))
        tile.paste(panel, (0, 0))
        tile.paste(art(picked).crop((0, 0, panel.width, 400)), (0, panel.height))
        columns.append(label(tile, fonts.LABELS[key] + (" (default)" if key == "atkinson" else ""), picked))
    sheet = Image.new("RGB", (sum(c.width for c in columns) + 12 * 3, columns[0].height), (6, 4, 11))
    x = 0
    for column in columns:
        sheet.paste(column, (x, 0))
        x += column.width + 12
    sheet.save(out / "fonts.png")
    before = label(shots["pixel"].crop(CROP).convert("RGB"), "Before: Pixel (Courier)", fonts.Choice("pixel"))
    after = label(shots["atkinson"].crop(CROP).convert("RGB"), "After: Atkinson Hyperlegible", fonts.Choice())
    pair = Image.new("RGB", (before.width * 2 + 12, before.height), (6, 4, 11))
    pair.paste(before, (0, 0))
    pair.paste(after, (before.width + 12, 0))
    pair.save(out / "before-after.png")
    fonts.apply(root, fonts.Choice())
    from cli_avatars.app import text_settings

    host.config, host._config_path = {}, stage._TMP / "config.json"
    host._build_config_ui = lambda win: text_settings.mount(host, win)
    host.dungeon.show_settings()
    for _ in range(3):
        root.update()
        time.sleep(0.1)
    film.grab().save(out / "settings.png")
    root.destroy()


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    finally:
        shutil.rmtree(stage._TMP, ignore_errors=True)
