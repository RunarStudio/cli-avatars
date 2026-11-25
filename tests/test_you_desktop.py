"""YOU-AVATAR desktop: the keeper walks by click and keys, the camera follows, bubbles open rows; off-screen child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_body_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_keeper_and_bubbles_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_you_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("keeper starts in the throne room", "keeper drawn", "no bubbles while nothing waits",
                     "floor click walks", "walk is a trip through the doors", "camera follows the walk",
                     "arrives in the clicked room", "room saved for the next start", "keys pan while not selected",
                     "click on the keeper selects it", "selection ring drawn", "selected keeper takes the key",
                     "held key walks it", "release stops", "walls stop the keys", "Esc lets go",
                     "keys pan again after Esc", "decision reaches its asker", "bubble over the asker",
                     "badge counts it", "asker taps without hook status", "no extra cue for a row", "bubble bobs",
                     "bubble readable at zoom 1", "bubble readable at zoom 3", "bubble click opens the row",
                     "hook blocked bubbles", "arrive cue for a new bubble", "cue held in focus",
                     "other tasks' rows wait in focus", "not opened before it gets there", "walking up opens the row", "opens once per approach",
                     "phone row carries the need", "phone keeper carries the badge", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
