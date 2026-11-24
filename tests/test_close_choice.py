"""BG.1: the Dungeon `x` asks Close or Minimize; Minimize keeps the app in the tray."""

import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_toolbar_kit
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli_avatars.desktop.settings import desktop_settings, with_on_close


class Prefs(unittest.TestCase):
    def test_default_is_ask(self):
        self.assertEqual(desktop_settings({}).on_close, "ask")

    def test_known_values_and_bad_values(self):
        for value in ("ask", "minimize", "quit"):
            self.assertEqual(desktop_settings({"desktop": {"on_close": value}}).on_close, value)
        for value in ("hide", 3, None, ""):
            self.assertEqual(desktop_settings({"desktop": {"on_close": value}}).on_close, "ask")

    def test_with_on_close_copies(self):
        config = {"desktop": {"bootcheck": False}}
        updated = with_on_close(config, "minimize")
        self.assertEqual(updated["desktop"], {"bootcheck": False, "on_close": "minimize"})
        self.assertEqual(config, {"desktop": {"bootcheck": False}})


class Flow(unittest.TestCase):
    def test_close_picker_minimize_and_tray(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_close_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("close asks", "picker in window", "esc cancels", "close quits", "enter minimizes",
                     "loop runs hidden", "notice once", "show restores", "remember minimize",
                     "remember quit", "settings row", "no tray iconifies", "tray menu",
                     "tray show", "tray quit"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
