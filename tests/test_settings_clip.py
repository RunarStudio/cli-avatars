"""LEFTOVERS: at 1920 px the right panel's Settings › Chat tiers and Settings › Bots lines and menus read in full."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_dock_tabs
import sys
import tempfile
import unittest
from pathlib import Path


class SettingsClip(unittest.TestCase):
    def test_chat_tiers_and_bots_read_in_full(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_settings_clip_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("right panel on Settings", "tier rows shown", "every Chat tab line reads in full",
                     "bots hidden", "every Bots tab line reads in full", "every Settings tab line reads in full"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
