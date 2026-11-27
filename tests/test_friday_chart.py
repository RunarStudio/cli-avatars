"""LEFTOVERS: the Friday burn-down parchment does not take floor clicks; its scroll button still hides it."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_you_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class FridayChart(unittest.TestCase):
    def test_floor_click_under_the_chart_walks(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_friday_chart_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("friday shows the chart", "the chart lies on a room's floor", "a floor click under the chart walks",
                     "the keeper arrives under the chart", "the chart stays up", "its scroll button keeps its click",
                     "the scroll button hides it"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
