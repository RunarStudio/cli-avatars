"""MESSENGER desktop: the courier walk, seal flash, lit card, ribbon, note, queue and focus hold, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_body_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_courier_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_courier_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("quiet without a decision", "nothing stored without a link", "a courier leaves the deciding room",
                     "bound for the affected room", "rustle cue on leave", "walks through the doors",
                     "courier drawn on the floor", "eased start", "moves along the path", "phone row for the walk",
                     "walk frames change in place", "a second courier queues", "queue pip on the walker", "arrives",
                     "seal flash on arrival", "stamp cue on arrival", "the affected card lights up",
                     "ribbon says where from", "never piles: the next waits its turn", "the queued one leaves after",
                     "needs-you row while the card waits", "tasks tile glows with the ribbon",
                     "click opens the note on the floor", "note shows the decision and the reason",
                     "opened stops the glow", "card and ribbon gone", "open task from the note", "note closes",
                     "focus holds a courier of another task", "its cues wait", "released after focus",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
