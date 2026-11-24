"""FIX.NAMEPLATES: a nameplate keeps one offset from its sprite while avatars idle, walk and pass each other."""

from __future__ import annotations

import subprocess  # noqa: TID251  # the Tk canvas runs in a child, like test_dungeon_rooms
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import nameplates  # noqa: E402


class _Scene:
    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600


def _avatar(aid, name):
    return SimpleNamespace(aw=48, ah=48, agent=SimpleNamespace(agent_id=aid), plate_text=lambda: f"{name}\nidle")


def _walk(scene, steps=60):
    """Mira idles; Orch walks left through her; Tess walks right below. Offsets per tick."""
    avs = {"mira": _avatar("mira", "Claude-1a2b"), "orch": _avatar("orch", "Claude-orch-9f"), "tess": _avatar("tess", "T")}
    offsets = {aid: set() for aid in avs}
    for step in range(steps):
        spots = {
            "mira": (400.0, 300.0),
            "orch": (520.0 - step * 3.7, 296.0 + step * 0.13),
            "tess": (300.0 + step * 2.9, 340.0 - step * 0.21),
        }
        nameplates.seat_inside(scene, sorted(avs), spots, avs, None)
        for aid, av in avs.items():
            sx = int(spots[aid][0] - av.aw / 2.0)
            sy = int(spots[aid][1] - av.ah / 2.0)
            left, top, _w, _h = av._label_box
            offsets[aid].add((left - sx, top - sy))
    return offsets


class PlateKeepsItsOffset(unittest.TestCase):
    def test_offset_is_constant_while_neighbours_walk_past(self):
        with patch.object(nameplates, "plate_pixels", lambda _scene, text: (8 * len(text.split("\n")[0]) + 6, 22)):
            offsets = _walk(_Scene())
        for aid, seen in offsets.items():
            self.assertEqual(len(seen), 1, f"{aid} plate moved against its sprite: {sorted(seen)}")

    def test_dragged_plate_follows_the_pointer(self):
        av = _avatar("mira", "Claude-1a2b")
        seen = set()
        with patch.object(nameplates, "plate_pixels", lambda _scene, _text: (94, 22)):
            for step in range(40):
                av.x, av.y = 200.0 + step * 2.3, 250.0 + step * 1.7
                nameplates.seat_inside(_Scene(), ["mira"], {}, {"mira": av}, av)
                left, top, _w, _h = av._label_box
                seen.add((left - int(av.x), top - int(av.y)))
        self.assertEqual(len(seen), 1, sorted(seen))

    def test_offset_is_constant_under_tk_scaling(self):
        proc = subprocess.run(  # noqa: TID251  # the Tk canvas runs in a child, like test_dungeon_rooms
            [sys.executable, str(Path(__file__).resolve()), "scaling"],
            cwd=ROOT, capture_output=True, text=True, timeout=60, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ok 1.25", proc.stdout)
        self.assertIn("ok 1.5", proc.stdout)


def _scaled() -> int:
    """Real Courier metrics at Windows-like Tk scaling: every plate keeps one offset."""
    try:
        import tkinter as tk

        root = tk.Tk()
    except Exception:
        return 77
    try:
        root.withdraw()
        for scaling in (1.25, 1.5):
            root.tk.call("tk", "scaling", scaling)
            scene = tk.Canvas(root, width=800, height=600)
            with patch.object(scene, "winfo_width", lambda: 800), patch.object(scene, "winfo_height", lambda: 600):
                offsets = _walk(scene)
            moved = {aid: sorted(seen) for aid, seen in offsets.items() if len(seen) != 1}
            if moved:
                print(f"scaling {scaling}: plates moved: {moved}")
                return 1
            print(f"ok {scaling}")
        return 0
    finally:
        root.destroy()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scaling":
        sys.exit(_scaled())
    unittest.main()
