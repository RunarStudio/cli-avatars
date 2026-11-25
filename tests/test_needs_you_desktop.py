"""NEEDS-YOU.1 desktop: the Dungeon's "Needs you (N)" dock tab, run off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk dock runs in a child, like test_toolbar_kit
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_needs_tab_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_needs_you_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("tab count", "first read quiet", "rows in order", "row text", "new item enters", "soft cue",
                     "in place", "no repeat cue", "click opens", "clear", "clear stored", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


    def test_card_opens_with_no_topic_selected(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_needs_open_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("empty board", "card shown", "same card"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
