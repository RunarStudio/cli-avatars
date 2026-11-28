"""Child process for ``test_noflicker``: the real Dungeon floor off-screen on made-up data, canvas writes counted.
Exit 77 without a display.

    python tests/_noflicker_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1. A write is a no-op when the item keeps its coords,
options and stacking (Tk repaints its area anyway).
"""

import collections
import importlib.util
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO))
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    tk.Tk().destroy()
except Exception:
    raise SystemExit(77)

spec = importlib.util.spec_from_file_location("shot_status_colors", REPO / "tools" / "shot_status_colors.py")
shot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shot)

from cli_avatars.app import cues, dungeon_nav, inside_roster, status_ink, timelapse_view  # noqa: E402
from cli_avatars.app.room_glow import glow_for  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402

CREATES = ("create_text", "create_image", "create_rectangle", "create_line", "create_oval", "create_polygon")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


class Counter:
    """Wraps the scene's write methods; ``on`` counts by caller ``file:line kind``."""

    def __init__(self, scene) -> None:
        self.scene, self.on = scene, False
        self.noop, self.change, self.made, self.text = (collections.Counter() for _ in range(4))
        for name in ("itemconfigure", "itemconfig"):
            self._wrap(name, self._same_conf)
        self._wrap("coords", self._same_coords)
        for name in ("tag_raise", "tag_lower", "lift", "lower"):
            self._wrap(name, self._same_order)
        self._wrap("delete", lambda a, k: False if any(scene.find_withtag(t) for t in a) else None)
        for name in CREATES:
            self._wrap(name, None)

    def _site(self) -> str:
        for frame in reversed(traceback.extract_stack()[:-2]):
            if str(REPO) in frame.filename and "_noflicker_probe" not in frame.filename:
                return f"{Path(frame.filename).relative_to(REPO)}:{frame.lineno}"
        return "?"

    def _wrap(self, name, same) -> None:
        real = getattr(self.scene, name)

        def write(*a, **k):
            if not self.on or (name == "coords" and len(a) <= 1) or (name.startswith("itemconf") and not k):
                return real(*a, **k)
            if same is None:
                self.made[f"{self._site()} {name}"] += 1
                return real(*a, **k)
            if name.startswith("itemconf") and "text" in k:
                self.text[a[0]] += 1
            before = same(a, k)
            if before is None:  # a delete that matches nothing repaints nothing
                return real(*a, **k)
            out = real(*a, **k)
            nothing = before() if callable(before) else before
            (self.noop if nothing else self.change)[f"{self._site()} {name}"] += 1
            if name == "delete":
                self.made[f"{self._site()} delete"] += 1
            return out

        setattr(self.scene, name, write)

    def _same_coords(self, a, k):
        new = a[1:] if len(a) > 2 else a[1]
        return [round(float(v), 1) for v in self.scene.coords(a[0])] == [round(float(v), 1) for v in new]

    def _same_conf(self, a, k):
        def text(v):
            return " ".join(map(str, v)) if isinstance(v, (tuple, list)) else str(v)
        return all(str(self.scene.itemcget(a[0], key)) == text(v) for key, v in k.items())

    def _same_order(self, a, k):
        order = self.scene.find_all()
        return lambda: self.scene.find_all() == order

    def reset(self) -> None:
        for c in (self.noop, self.change, self.made, self.text):
            c.clear()


def frames(stage, count: int, start: float) -> float:
    now = start
    for _ in range(count):
        now += 0.05
        stage.book._now = now
        stage.book.draw_inside()
        status_ink.sweep(stage.book)
        timelapse_view.paint(stage.book)
        dungeon_nav.paint(stage.book)
        stage.root.update()
    return now


def main() -> None:
    cues.play = lambda _app, _name: None
    inside_roster.Hall.paint_user = lambda *_a: None
    shot.AGENTS = tuple((f"a{i}b2c3d4", name, i) for i, name in enumerate(("Orrin", "Vessa", "Tamsin", "Bram", "Ilse",
                                                                          "Corwin")))
    load_sprites(REGISTRY)
    stage = shot.Stage()
    stage.agents["a1b2c3d4"].subagents = 2
    stage.tick(1.0)
    scene = stage.scene
    count = Counter(scene)
    now = frames(stage, 20, time.time())
    count.on = True
    now = frames(stage, 50, now)
    count.on = False
    noop = sum(count.noop.values())
    check("no no-op repaint over 50 idle frames", noop == 0, f"{noop}: {count.noop.most_common(12)}")
    made = sum(count.made.values())
    check("no item re-created over 50 idle frames", made == 0, f"{made}: {count.made.most_common(8)}")
    labels = {av.lbl_id for av in stage.host._inside.values() if av.lbl_id}
    rewrites = sum(n for item, n in count.text.items() if item in labels)
    check("no nameplate rewrite while the state stays", rewrites == 0, str(rewrites))

    room = "moon-forge"
    glow_for(stage.book).frame(room, now)
    now = frames(stage, 10, now)
    count.reset()
    count.on = True
    now = frames(stage, 20, now)
    count.on = False
    glowing = {k: v for k, v in (count.noop + count.change).items() if "room_glow.py" in k}
    check("the held room glow writes nothing", not glowing, str(glowing))

    aid = "a0b2c3d4"
    stage.set(aid, "error")
    count.reset()
    count.on = True
    frames(stage, 20, now)
    count.on = False
    label = stage.host._inside[aid].lbl_id
    check("a state change writes the plate once", count.text.get(label, 0) <= 2, str(count.text.get(label, 0)))

    from types import SimpleNamespace

    from cli_avatars.app.throne_panel import ThronePanel

    jobs, refreshed = [], []
    canvas = SimpleNamespace(pack=lambda **_k: None, after=lambda ms, _fn: jobs.append(ms))
    panel = SimpleNamespace(canvas=canvas, _live=False, _frames=[1, 2], _frame=0, _draw=lambda: None,
                            _refresh=lambda: refreshed.append(1))
    panel._flicker = lambda: ThronePanel._flicker(panel)
    ThronePanel.show(panel)
    check("the throne tab starts no repeating timer", refreshed == [1] and jobs == [], f"{refreshed} {jobs}")
    stage.root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(shot._TMP, ignore_errors=True)
