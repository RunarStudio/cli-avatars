"""Headless tick cost for walking avatars.

``cached`` is the overlay path: one PhotoImage per key, then coords.
``naive`` builds a new PhotoImage and a new canvas item every frame.
Both use a withdrawn Tk root. Prints median milliseconds per tick.
"""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _NaivePhotos:
    """Call the factory and wrap every PIL image in a fresh PhotoImage."""

    def get(self, key, factory):
        from PIL import Image, ImageTk

        made = factory()
        if isinstance(made, Image.Image):
            return ImageTk.PhotoImage(made)
        return made


def _agents(n: int):
    from cli_avatars.model.agent import AgentInfo, S
    from cli_avatars.world.avatar import Avatar

    avatars = []
    for i in range(n):
        agent = AgentInfo(agent_id=f"a{i}", name=f"a{i}", status=S.BUSY)
        avatars.append(Avatar(agent, 1280, 800, i, registry=None))
        avatars[-1].y = 700.0
        avatars[-1].on_ground = True
    return avatars


def _run(mode: str, n: int, ticks: int) -> float:
    import tkinter as tk

    from cli_avatars.app.render import PhotoCache

    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=1280, height=800, highlightthickness=0)
    avatars = _agents(n)
    photos = PhotoCache() if mode == "cached" else _NaivePhotos()
    samples = []
    floors = [(0, 760, 1280, None)]
    for _ in range(ticks):
        t0 = time.perf_counter()
        for av in avatars:
            av.update(floors)
            if mode == "naive":
                if av.spr_id:
                    canvas.delete(av.spr_id)
                    av.spr_id = None
                if av.lbl_id:
                    canvas.delete(av.lbl_id)
                    av.lbl_id = None
                av._draw_sig = None
            av.draw(canvas, photos)
        canvas.update_idletasks()
        samples.append((time.perf_counter() - t0) * 1000)
    root.destroy()
    # Match the terrain log: drop the first half, then take the median.
    body = samples[len(samples) // 2 :]
    return statistics.median(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cached", "naive", "both"), default="both")
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--ticks", type=int, default=120)
    args = parser.parse_args()
    modes = ("naive", "cached") if args.mode == "both" else (args.mode,)
    for mode in modes:
        ms = _run(mode, args.n, args.ticks)
        print(f"{mode} N={args.n} M={args.ticks} median {ms:.3f} ms/tick")


if __name__ == "__main__":
    main()
