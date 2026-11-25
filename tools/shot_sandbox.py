"""SANDBOX evidence: Try it risky on two task cards, their chambers on the Dungeon floor with the chat's avatar
inside, then Promote one (the seal) and Bin the other (the trapdoor).

Made-up topic, cards and a git fixture repo with made-up names in a temporary folder; no CLI starts (the chat's
avatar is a made-up session in the sandbox's folder). It draws the real Dungeon window and grabs the screen, so run
it under Xvfb:

    xvfb-run -a python tools/shot_sandbox.py <out-dir>

Writes ``sandbox.gif`` and ``desktop-1366.png``. ``seed`` gives the same data for a phone shot.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _path in (_ROOT, _ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

W, H = 1366, 960
TOPIC, PROJECT = "west-keep", "lantern-works"
TITLES = ("Wild wick idea", "Brass lantern idea")


def seed(base: Path) -> tuple[Path, list[str]]:
    """A data dir with the made-up topic in a fixture repo and two cards; their ids."""
    from registry.facade import Registry
    from test_sandbox import make_repo, pick_folder
    from topics import set_topic

    data = base / "data"
    data.mkdir()
    repo = make_repo(base)
    set_topic(data, TOPIC, title="West keep", project=PROJECT, status="open")
    pick_folder(data, TOPIC, repo)
    reg = Registry(data)
    return data, [reg.task_create(PROJECT, title, topic=TOPIC)["id"] for title in TITLES]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="sandbox-shot-"))
    os.environ["CLI_AVATARS_DATA_DIR"] = str(base / "appdata")
    try:
        film(base, out)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir()) if p.is_file()))


def film(base: Path, out: Path) -> None:
    import tkinter as tk
    from types import SimpleNamespace

    from PIL import ImageDraw, ImageFont, ImageGrab

    import sandbox
    from cli_avatars.app import cues, inside_roster
    from cli_avatars.app.dungeon_rooms import paint_rooms
    from cli_avatars.app.dungeon_window import DungeonWindow
    from cli_avatars.app.places import PlaceBook
    from cli_avatars.app.render import PhotoCache
    from cli_avatars.model.agent import AgentInfo
    from cli_avatars.model.place import INSIDE, Place
    from cli_avatars.sprites.registry import REGISTRY, load_sprites
    from cli_avatars.world.avatar import Avatar

    data, cards = seed(base)
    cues.play = lambda *_a: None
    root = tk.Tk()
    load_sprites(REGISTRY)
    noop = lambda *_a, **_k: None  # noqa: E731
    agents = {"a1b2c3d4": AgentInfo("a1b2c3d4", "Orrin", status="idle", skin="ember_mage", source="claude",
                                    project=PROJECT, last_seen=time.time())}
    app = SimpleNamespace(root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop,
                          _toggle_chat=noop, _create_hud_win=noop, bots=None, _chat_window=None, _drag_av=None,
                          _chat_directory=lambda: data, scanner=SimpleNamespace(get_agents=lambda: agents),
                          render=SimpleNamespace(photos=PhotoCache()), _show_chat=noop, _inside={})
    view = DungeonWindow(app)
    app.dungeon = view
    view.build(offscreen=True)
    root.deiconify()
    root.geometry(f"{W}x{H}+0+0")
    view.set_left(False)
    view.set_right(False)
    book = PlaceBook(app, path=None)
    app.places = book
    hall = inside_roster.hall(book)
    hall._talk = lambda: []
    hall._rooms = lambda: ([], [])

    def arrive(aid: str, name: str, skin: str, project: str) -> None:
        agents[aid] = AgentInfo(aid, name, status="busy", skin=skin, source="claude", project=project,
                                last_seen=time.time())
        app._inside[aid] = Avatar(agents[aid], 800, 600, 0, REGISTRY, spring_mode=True)
        book._actors[aid] = Place(aid, INSIDE, "new", None)

    arrive("a1b2c3d4", "Orrin", "ember_mage", PROJECT)
    agents["a1b2c3d4"].status = "idle"
    frames, raw, font = [], [], ImageFont.load_default(size=15)

    def shot():
        x, y = root.winfo_rootx(), root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + W, y + H), xdisplay=os.environ.get("DISPLAY"))

    def grab(text: str, hold: int = 1):
        for _ in range(3):
            root.update()
        image = shot()
        raw.append(image.copy())
        if text:
            draw = ImageDraw.Draw(image)
            w = int(draw.textlength(text, font=font)) + 28
            draw.rectangle((14, H - 48, 14 + w, H - 14), fill=(23, 16, 34), outline=(224, 170, 62), width=2)
            draw.text((28, H - 40), text, fill=(240, 230, 200), font=font)
        frames.extend([image] * hold)
        return image

    def floor(seconds: float, text: str, every: float = 0.12):
        view.show_center("dungeon")
        root.update()
        paint_rooms(view.scene)
        end = time.time() + seconds
        while time.time() < end:
            book._now = time.time()
            book.draw_inside()
            grab(text)
            time.sleep(max(0.0, every - 0.05))

    def card(index: int):
        view.show_center("tasks")
        panel = app._tasks_panel
        panel.refresh(force=True)
        panel.open_card(cards[index])
        root.update()
        return panel.card_panel.sandbox

    floor(1.2, "The Dungeon: Orrin in the Apothecary")
    slip = card(0)
    grab("Task card: the Sandbox slip offers Try it risky", 8)
    slip.try_button.invoke()
    grab("Try it risky: a worktree on its own sandbox/ branch, and a task chat that works there", 12)
    first = sandbox.for_card(data, cards[0])
    arrive("e5f6a7b8", "Claude", "frost_wanderer", Path(first["path"]).name)
    floor(3.0, "Enter in its chat: the sandbox chamber cracks open off the Apothecary, the avatar works inside")
    slip = card(1)
    slip.try_button.invoke()
    second = sandbox.for_card(data, cards[1])
    arrive("c9d0e1f2", "Claude", "ember_mage", Path(second["path"]).name)
    grab("A second wild idea, a second sandbox", 8)
    floor(2.6, "Two throwaway chambers: rune fence, ember cracks, a warning brazier")
    raw[-1].save(out / "desktop-1366.png")
    slip = card(0)
    grab("Promote (the seal): keep the branch; no merge, no push", 8)
    slip.promote_button.invoke()
    floor(2.2, "Promoted: the chamber is sealed in gold and fades out")
    card(0)
    grab("The branch name stays on the card to copy", 10)
    (Path(second["path"]) / "flame.py").write_text("FLAME = 'too wild'\n", encoding="utf-8")
    slip = card(1)
    slip.bin_button.invoke()
    grab("Bin (the trapdoor): uncommitted changes, so it asks once more", 12)
    slip.confirm_button.invoke()
    floor(2.4, "Binned: worktree removed, its sandbox branch deleted; the chamber drops through its trapdoor")
    card(1)
    grab("Try it risky is offered again", 8)
    frames[0].save(out / "sandbox.gif", save_all=True, append_images=frames[1:], duration=120, loop=0,
                   optimize=True)
    root.destroy()


if __name__ == "__main__":
    main()
