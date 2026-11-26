"""PARK.1 desktop: the park, idle objects and task routing on the Dungeon floor, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_body_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_park_and_idle_life_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_park_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("park on the floor", "busy avatars stay home", "park drawn", "idle objects drawn",
                     "task tables drawn", "short idle takes an object", "walks there through the doors",
                     "stands at it", "object reserved", "in use loop drawn", "long idle goes to the park",
                     "reaches the park", "phone rows carry the idle act", "park ambience", "busy releases the spot",
                     "walks back", "back in its room", "assigning walks it to the card's room",
                     "arrives in the card's room", "works at the table",
                     "a task chat walks its session to the card's room", "done sends it home", "held in focus",
                     "park off in config", "long idle falls back to an object", "idle objects off in config",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
