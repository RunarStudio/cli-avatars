"""BOSS-ROOM.1 desktop: the Oni Pit grows and shrinks with dust and a grind, the Crypt's skulls drop in, off-screen."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_boss_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_boss_rooms_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_boss_room_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("oni pit and crypt on the floor", "no backlog: bare pit, empty crypt", "niches line the crypt walls",
                     "the pit grows a tile a step", "dust along the moving walls", "grind as the walls slide",
                     "the oni sits in the pit", "forgotten cards drop in as skulls", "rattle on a new skull",
                     "each skull in its niche", "the crypt grows with the count", "the plaque counts them",
                     "hover shows title and days forgotten", "leaving hides it", "click opens the card",
                     "a done card's skull leaves", "the others keep their niches",
                     "focus holds the rattle of another task", "held rattle plays after focus",
                     "cards close: the pit shrinks back", "and the crypt empties", "HP 0: bare room, no oni",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
