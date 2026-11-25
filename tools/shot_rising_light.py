"""SELECT-LIGHT.1 evidence: a Topics row click and the selected room's light rising from its floor.

Made-up rooms, names and cards (the ORCH.ROOM stage of ``shot_orch_rooms``) in a temporary data folder, removed
after. Draws the real Dungeon floor on a Tk canvas and grabs the screen, so run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_rising_light.py <out-dir>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shot_orch_rooms as orch_shot  # noqa: E402
from shot_orch_rooms import caption  # noqa: E402

from cli_avatars.app import orch_dock  # noqa: E402

orch_shot.W, orch_shot.H = 1366, 768
STEP, EVERY = 0.025, 0.075


def click(stage, topic: str) -> None:
    for frame in stage.dock.winfo_children():
        labels = [w for w in frame.winfo_children() if hasattr(w, "cget")]
        if labels and topic in str(labels[0].cget("text")):
            labels[0].event_generate("<Button-1>")
            stage.root.update()
            return
    raise SystemExit(f"no Topics row for {topic}")


def main() -> None:
    import tkinter as tk

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    orch_shot.load_sprites(orch_shot.REGISTRY)
    root = tk.Tk()
    root.geometry(f"{orch_shot.W}x{orch_shot.H}+0+0")
    stage = orch_shot.Stage(root)
    orch_dock.time = SimpleNamespace(time=lambda: stage.clock[0])
    stage.tick(12.0)
    orch_dock.render(stage.app, stage.dock, orch_dock.rows(stage.app))
    stage.tick(0.5)
    box = (orch_shot.DOCK, 0, orch_shot.W, orch_shot.H)
    frames = []

    def film(seconds: float, text: str) -> None:
        for _ in range(round(seconds / EVERY)):
            stage.tick(EVERY, STEP)
            frames.append(caption(stage.grab(box), text))

    film(0.6, "Topics: nothing selected")
    click(stage, "release-train")
    film(0.35, "Click release-train: light rises from its floor")
    stage.grab().save(out / "desktop-1366.png")
    film(2.25, "Click release-train: light rises from its floor")
    click(stage, "harbor-map")
    film(2.6, "Click harbor-map: the light moves there")
    film(0.9, "The frame ends: the drops fade with the glow")
    frames[0].save(out / "rising-light.gif", save_all=True, append_images=frames[1:], duration=round(EVERY * 1000),
                   loop=0, optimize=True)
    root.destroy()
    shutil.rmtree(orch_shot._DATA, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
