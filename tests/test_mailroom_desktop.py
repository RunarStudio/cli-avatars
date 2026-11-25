"""MAILROOM desktop: the Mailroom tab of the Dungeon (letters land, keys approve, bounce and retopic in place, one
cue per batch, held while focused), the capture strip's Mail toggle and the two cues. Tk runs in a child process.
"""

import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_quick_capture
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_mailroom import seed  # noqa: E402


class Cues(unittest.TestCase):
    def test_letter_and_filed_are_their_own_short_wavs(self):
        from cli_avatars.app import cues

        letter, filed = cues.wav("letter"), cues.wav("filed")
        self.assertEqual((letter[:4], filed[:4]), (b"RIFF", b"RIFF"))
        self.assertNotEqual(letter, filed)
        self.assertNotIn(letter, (cues.wav("arrive"), cues.wav("capture"), cues.wav("move")))
        self.assertLess(len(letter), cues.RATE * 2 * 0.6)
        self.assertEqual(filed, cues.wav.__wrapped__("filed"))


class Art(unittest.TestCase):
    def test_letters_fill_the_shelf_with_the_count(self):
        from cli_avatars.app import mail_art

        empty, some, more = (mail_art.letters(n) for n in (0, 3, 20))
        self.assertIsNone(empty.getbbox())
        self.assertLess(sum(some.split()[3].histogram()[1:]), sum(more.split()[3].histogram()[1:]))
        self.assertEqual(mail_art.room(800, 600).size, (800, 600))


class Tab(unittest.TestCase):
    def test_mailroom_tab_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_mailroom_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("tab opens the room", "three letters land", "one letter cue for the batch", "tab counts",
                     "sorter topics", "draft decision shown", "task chat proposed", "enter approves", "filed cue",
                     "t picks the next topic", "slip changed in place", "b bounces to unsorted", "held while focused",
                     "released after focus", "needs-you row opens the room", "capture mail posts", "no new toplevel",
                     "no callback errors"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
