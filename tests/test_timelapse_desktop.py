"""TIMELAPSE desktop: the scrubber, ghosts and open-at-moment on the Dungeon floor, run off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_daily_recap_desktop
import sys
import tempfile
import unittest
from pathlib import Path

from cli_avatars.app import cues


class Desktop(unittest.TestCase):
    def test_time_lapse_on_the_floor_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_timelapse_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("entry plate", "room log kept", "entry click", "covers the live floor", "previous day",
                     "ghost in the task's room", "walks between rooms", "in place", "trail motes", "arrives",
                     "map tinted to the hour", "scrub with a tick", "drag scrubs", "gem click opens the chat",
                     "chat scrolled to that message", "moment cue", "ghost click opens its chat at that time",
                     "plays forward", "space pauses", "held in focus", "cue after focus", "esc returns live",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)

    def test_tick_and_moment_are_their_own_sounds(self):
        tick, moment = cues.wav("tick"), cues.wav("moment")
        self.assertTrue(tick.startswith(b"RIFF") and moment.startswith(b"RIFF"))
        self.assertEqual(tick, cues.wav("tick"))
        others = tuple(cues.wav(n) for n in ("arrive", "decide", "scroll", "risky"))
        self.assertNotIn(tick, others)
        self.assertNotIn(moment, others + (tick,))


if __name__ == "__main__":
    unittest.main()
