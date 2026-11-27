"""LEFTOVERS: a room decision opened from Needs you shows in the room chat (on the Inbox), not behind Grok."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_dock_tabs
import sys
import tempfile
import unittest
from pathlib import Path


class NeedsDecision(unittest.TestCase):
    def test_decision_opens_on_the_inbox(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_needs_decision_probe.py"), str(root),
                 str(Path(tmp) / "data"), str(Path(tmp) / "work")],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("decision in Needs you", "room chat open on the room", "the chat is on the Inbox",
                     "the decision shows", "no CLI ran"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
