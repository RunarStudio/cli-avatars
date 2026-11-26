"""BACKLOG-BOSS desktop: the oni in its pit, hits, list, chart, cues and focus hold, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_courier_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_boss_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_boss_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("pit in the oni pit", "bare room at HP 0",
                     "quiet midweek: no bar, no chart", "blocked and stale cards feed it", "pit and oni drawn",
                     "grows a stage and roars",
                     "idle breathing frames change in place", "hover shows HP and the feeding tasks",
                     "hover shows the bar", "click lists them, rows open", "a row opens its card", "list closes",
                     "a close plays a hit", "thud cue on the hit", "hit flash", "damage number rises",
                     "bar shows the drop", "shake", "HP drops", "one hit per close", "b key shows the burn-down",
                     "scroll button hides it", "focus holds the cue of another task", "held cue plays after focus",
                     "friday shows the bar and the chart", "last hit plays the fanfare", "defeated",
                     "store is owner-only", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
