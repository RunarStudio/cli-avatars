"""LEFTOVERS: the chat window's room cards read the one palette (``status_palette``), in a child process."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_bot_dots
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RoomCardDots(unittest.TestCase):
    def test_room_card_dots_use_the_one_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_room_card_dots_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ok each state has its palette dot", proc.stdout)


if __name__ == "__main__":
    unittest.main()
