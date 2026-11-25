"""BODY desktop: poses, the bench and door walks, smoke, hover and cues on the Dungeon floor, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_timelapse_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_body_language_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_body_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=180, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("idle by default", "benches by the rooms", "bench items on the floor", "no smoke yet",
                     "flowing strides", "stride frame drawn", "blocked card slumps", "sigh cue",
                     "walks with a trip through the doors", "sits on the bench", "seat on its room's bench",
                     "not sent to the user", "slump frame drawn", "open decision taps", "held in focus",
                     "waits at the door", "door spot inside its room", "door spot on the way to the user",
                     "tap frame drawn", "long run smokes", "smoke items drawn", "crackle cue", "thicker with time",
                     "smoke drifts in place", "items changed in place", "hover shows the word", "hover leaves",
                     "phone rows carry the pose", "phone rows carry the smoke", "cleared stands up",
                     "walks back home", "off in config", "needs walk back when off", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
