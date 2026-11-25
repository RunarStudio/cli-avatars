"""SKIN: the skin picker opens on the clicked avatar, browses, and Apply changes that avatar for good."""

import subprocess  # noqa: TID251  # the Tk picker runs in a child, like test_avatar_menu
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS = (
    "opens on the clicked avatar", "shows the skin the map draws", "browse and select a card",
    "apply changes the selected avatar", "apply is kept on disk", "apply plays a cue", "apply closes the panel",
    "reopens on the picked skin", "a bot avatar is the one selected", "a bot avatar gets the skin",
    "focus holds the cue", "restart and rescan keep it",
)


class SkinPicker(unittest.TestCase):
    def test_skin_picker_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_skin_picker_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        for name in CHECKS:
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
