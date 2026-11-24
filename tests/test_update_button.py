"""UPDATE.1: an Update button on the Dungeon toolbar calls the existing update flow."""

import subprocess  # noqa: TID251  # the Tk toolbar runs in a child, like test_toolbar_kit
import sys
import unittest
from pathlib import Path

from cli_avatars.app import toolbar_kit as kit

ROOT = Path(__file__).resolve().parent.parent


class Kit(unittest.TestCase):
    def test_update_is_a_window_action_with_an_icon(self):
        self.assertEqual(kit.kind("update"), kit.WINDOW)
        self.assertIn("update", kit.tip("update"))
        self.assertNotEqual(kit.icon_rows("update", False), kit.icon_rows("update", True))


class Button(unittest.TestCase):
    def test_update_button_off_screen(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_update_button_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("in window group", "checking at start", "missing tool", "from source", "reason as tooltip",
                     "enabled", "click calls start_update", "running", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
