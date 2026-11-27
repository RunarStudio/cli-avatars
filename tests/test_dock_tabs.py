"""LEFTOVERS: the right panel's Pop out and tabs fit it at 1366 px; every Settings tab name reads in full."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_leftovers_ui
import sys
import tempfile
import unittest
from pathlib import Path


class DockTabs(unittest.TestCase):
    def test_pop_out_and_settings_names(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_dock_tabs_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("both side panels open", "Pop out inside the right panel", "every right tab left of Pop out",
                     "Settings built", "every Settings tab name reads in full", "a tab name opens its tab",
                     "the selected tab is marked"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
