"""PHONE-VOICE evidence on the desktop: the answer said on the phone lands in the Dungeon through the usual stores.

The made-up day of ``shot_courier``: Orrin asks in the Moon forge whether to ship on Friday (the question names the
Glass apple orchard). The transcript "approve, ship it Friday" goes through ``voice.parse`` and the decision answer,
as the phone's confirm tap does; the messenger then walks the answer to the orchard and its card lights up. It draws
the real Dungeon floor on Tk and grabs the screen, so run it under Xvfb:

    xvfb-run -a python tools/shot_voice.py <out-dir>

Writes ``desktop-1366.png``. The data dir is a fresh temp dir, removed after.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_courier as sc  # noqa: E402
import shot_phone_voice as spv  # noqa: E402

import voice  # noqa: E402
from cli_avatars.app import courier_view, cues  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from registry.facade import Registry  # noqa: E402
from webui import scene  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    try:
        load_sprites(REGISTRY)
        cues.play = lambda _app, _name: None
        root = sc.tk.Tk()
        root.geometry(f"{sc.W}x{sc.H}+0+0")
        stage = sc.Stage(root)
        stage.tick(1.0)
        row = spv.ask(stage.cards)
        decision = next(d for d in scene.decisions(sc._DATA) if d["id"] == row["id"])
        act = voice.parse("approve, ship it Friday", decision)
        Registry(sc._DATA).decision_answer(row["id"], act["choice"], act["text"] or None)
        view = courier_view.view_for(stage.book)
        view.reread()
        stage.tick(1.0)
        while view.walk is not None and view.walk.done < 0.97:
            stage.tick(0.45)
        stage.tick(1.2)
        view.reread()
        stage.tick(1.0)
        view.open(next(iter(view.lit.values()))["key"])
        stage.tick(1.5)
        stage.grab().save(out / "desktop-1366.png")
        root.destroy()
    finally:
        shutil.rmtree(sc._DATA, ignore_errors=True)
    print("wrote", out / "desktop-1366.png")


if __name__ == "__main__":
    main()
