"""Burst and glitch effects on a fake canvas. No Tk."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.effects.burst import BurstEffect  # noqa: E402
from cli_avatars.effects.glitch import GlitchFlash  # noqa: E402


class _Canvas:
    def __init__(self):
        self._next = 1
        self.created = []
        self.deleted = []
        self.moved = []

    def create_oval(self, *args, **kwargs):
        item = self._next
        self._next += 1
        self.created.append(("oval", item))
        return item

    def create_rectangle(self, *args, **kwargs):
        item = self._next
        self._next += 1
        self.created.append(("rect", item))
        return item

    def coords(self, item, *args):
        self.moved.append(item)

    def delete(self, item):
        self.deleted.append(item)


class TestEffects(unittest.TestCase):
    def test_imports_with_tkinter_blocked(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.modules['tkinter']=None\n"
             "import cli_avatars.effects.burst\n"
             "import cli_avatars.effects.glitch\n"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("tkinter", sys.modules)

    def test_burst_creates_then_deletes_each_particle(self):
        canvas = _Canvas()
        burst = BurstEffect(10, 20, "#ffffff", n=8, life=4, speed_max=2.0)
        alive = True
        steps = 0
        while alive and steps < 20:
            alive = burst.tick(canvas)
            steps += 1
        self.assertFalse(alive)
        ovals = [item for kind, item in canvas.created if kind == "oval"]
        self.assertEqual(len(ovals), 8)
        self.assertEqual(sorted(canvas.deleted), sorted(ovals))
        burst.cleanup(canvas)

    def test_glitch_replaces_cells_until_life_ends(self):
        canvas = _Canvas()
        flash = GlitchFlash(canvas, 0, 0, 40, 40, pink=True)
        self.assertGreaterEqual(len(canvas.created), 6)
        first = len(canvas.created)
        ticks = 0
        while flash.tick() and ticks < 30:
            ticks += 1
        self.assertEqual(ticks, GlitchFlash.LIFE - 1)
        self.assertGreater(len(canvas.created), first)
        self.assertEqual(len(canvas.deleted), len(canvas.created))
        self.assertFalse(flash.tick())


if __name__ == "__main__":
    unittest.main()
