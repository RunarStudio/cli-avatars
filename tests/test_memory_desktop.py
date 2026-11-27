"""MEMORY.1: the Memory tab in the Dungeon: Create, Remember from a chat line, Consolidate now, tree, hash, cues."""

import subprocess  # noqa: TID251  # the Tk panel runs in a child, like test_repos
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Tk(unittest.TestCase):
    def test_memory_tab_remember_consolidate_and_pin(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_memory_probe.py"), str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("memory tab", "missing root says so", "create lays out", "chat offers remember", "form filled",
                     "inbox +1", "remember cue", "app wrote only the inbox", "consolidated", "hash shown",
                     "consolidated cue", "tree and next action", "pin offered", "pinned topic gets a room",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
