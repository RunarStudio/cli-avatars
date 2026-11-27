"""LEFTOVERS: the open task card follows an agent's title, notes and progress edits."""

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_dock_tabs
import sys
import tempfile
import unittest
from pathlib import Path


class CardFollow(unittest.TestCase):
    def test_open_card_follows_agent_edits(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_card_follow_probe.py"), str(root), data],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("agent_title_in_the_header", "agent_title_in_the_field", "agent_notes_in_the_field",
                     "agent_progress_in_the_field", "agent_note_in_the_field", "agent_edit_keeps_the_open_card",
                     "typed_title_stays", "agent_progress_moves_on", "typed_title_saves",
                     "saved_title_in_the_header"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
