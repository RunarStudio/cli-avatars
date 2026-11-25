"""DAILY-RECAP desktop: the Dungeon's Recap scroll tab, run off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_needs_you_desktop
import sys
import tempfile
import unittest
from pathlib import Path

from cli_avatars.app import cues


class Desktop(unittest.TestCase):
    def test_recap_tab_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_daily_recap_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("recap tab", "shown", "scroll cue", "today", "grouped", "lines", "live", "in place",
                     "previous day", "next stops at today", "kept window", "click opens card", "cue on open",
                     "no new toplevel", "tally fed"):
            self.assertIn(f"ok {name}", proc.stdout)

    def test_scroll_cue_is_its_own_sound(self):
        blob = cues.wav("scroll")
        self.assertTrue(blob.startswith(b"RIFF"))
        self.assertEqual(blob, cues.wav("scroll"))
        self.assertNotIn(blob, tuple(cues.wav(n) for n in ("arrive", "decide", "move", "capture")))


if __name__ == "__main__":
    unittest.main()
