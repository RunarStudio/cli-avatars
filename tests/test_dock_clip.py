"""LEFTOVERS: at 1920 px the chat dock's Run row, the Grok topics strip and the task card read in full."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_settings_clip
import sys
import tempfile
import unittest
from pathlib import Path


class DockClip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as work:
            cls.proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_dock_clip_probe.py"), str(root), data, work],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )

    def setUp(self):
        if self.proc.returncode == 77:
            self.skipTest("tkinter has no display")
        out = self.proc.stdout + self.proc.stderr
        for name in ("chat docked on the room", "Grok strip shown", "task card open", "no CLI ran"):
            self.assertIn(f"ok {name}", self.proc.stdout, out)

    def assertChecks(self, *names):
        for name in names:
            self.assertIn(f"ok {name}", self.proc.stdout, self.proc.stdout + self.proc.stderr)

    def test_run_row_reads_in_full(self):
        self.assertChecks("Run and controls rows read in full", "every composer line reads in full")

    def test_grok_strip_reads_in_full(self):
        self.assertChecks("Grok topics strip reads in full")


if __name__ == "__main__":
    unittest.main()
