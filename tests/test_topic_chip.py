"""LEFTOVERS: the Topics dock's topic status chip ("open") is never clipped at 1366 px, in a child process."""

import subprocess  # noqa: TID251  # the Tk dock runs in a child, like test_rooms_dock
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TopicChip(unittest.TestCase):
    def test_chip_is_whole_at_1366(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_topic_chip_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("ok chip whole and inside its card"), 2, proc.stdout)


if __name__ == "__main__":
    unittest.main()
