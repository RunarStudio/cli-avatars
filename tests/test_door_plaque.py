"""DOOR-COUNTS desktop: a plaque on each room's door, updated in place, hover and click show the breakdown."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_needs_you_desktop
import sys
import tempfile
import unittest
from pathlib import Path

from cli_avatars.app import door_plaque


class Plaque(unittest.TestCase):
    def test_a_pending_decision_adds_the_seal(self):
        quiet = door_plaque.plaque_image({"orchestrators": 1, "agents": 2})
        waiting = door_plaque.plaque_image({"orchestrators": 1, "agents": 2, "decisions": 1})
        self.assertGreater(waiting.width, quiet.width)
        red = sum(1 for px in waiting.getdata() if px[3] and px[0] > 150 and px[1] < 80)
        self.assertGreater(red, 40)
        self.assertEqual(sum(1 for px in quiet.getdata() if px[3] and px[0] > 150 and px[1] < 80), 0)

    def test_empty_counts_draw(self):
        self.assertGreater(door_plaque.plaque_image({}).width, 20)
        self.assertGreater(door_plaque.tip_image("Apothecary", {}).height, 20)


class Desktop(unittest.TestCase):
    def test_plaques_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_door_plaque_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("one plaque per room", "counts", "steady", "decision counted", "in place", "hover shows",
                     "leave hides", "click pins", "click unpins", "no new toplevel", "no sound", "totals rows",
                     "totals above topics", "totals steady", "totals in place", "totals hover", "project gone"):
            self.assertIn(f"ok {name}", proc.stdout)

    def test_pointer_resting_on_a_plaque_edge_shows_once(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_door_plaque_hover_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("edge shows", "loop ticks", "show once"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
