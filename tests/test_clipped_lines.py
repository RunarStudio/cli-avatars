"""LEFTOVERS: at 1366 px the Settings update lines (the red PyInstaller reason) wrap."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_dock_tabs
import sys
import tempfile
import unittest
from pathlib import Path


class ClippedLines(unittest.TestCase):
    def test_update_lines_wrap(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_clipped_lines_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("both side panels open", "update lines shown", "every Settings update line reads in full"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
