"""AVATAR.MENU: click an avatar for Chat / Grab / Skin; the skin picker is a panel in the Dungeon, not a tab."""

import subprocess  # noqa: TID251  # the Tk menu runs in a child, like test_toolbar_kit
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS = (
    "no skins tab", "click shows menu", "move to room kept", "click does not open chat", "menu in kit frame",
    "chat via menu", "rooms listed", "move to room", "outside click closes menu", "esc closes menu",
    "hold drag moves, no menu", "grab picks up", "grabbed follows pointer", "next click drops",
    "skin panel in window", "panel in kit frame", "avatar preselected", "apply changes skin and closes",
    "esc closes panel", "outside click closes panel", "empty click shows nothing", "menu clamped to window",
)


class AvatarMenu(unittest.TestCase):
    def test_avatar_menu_off_screen(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_avatar_menu_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        for name in CHECKS:
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
