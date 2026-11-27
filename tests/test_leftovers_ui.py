"""LEFTOVERS UI: Memory tab inside the strip at 1366 px, Settings tabs scroll, the tour stays off the centre view."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_you_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class LeftoversUi(unittest.TestCase):
    def test_strip_settings_scroll_and_tour(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_leftovers_ui_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("both side panels open", "every centre tab inside the strip", "every centre tab on top, clickable",
                     "Memory tab shown",
                     "tab content is taller than the tab", "starts at the top", "the wheel scrolls it",
                     "a row added later scrolls it too", "tour first step shown", "callout off the centre view"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
