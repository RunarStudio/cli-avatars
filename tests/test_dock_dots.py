"""LEFTOVERS: the Topics dock's state dots read the one palette (``status_ink``), in a child process."""

import subprocess  # noqa: TID251  # the Tk dock runs in a child, like test_rooms_dock
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DockDots(unittest.TestCase):
    def test_dots_use_the_one_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_dock_dots_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("every state has its palette dot", "no dot outside the palette"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
