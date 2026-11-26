"""PROJECTS.1 desktop: the Projects tab in the one Dungeon window, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_repos
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_projects_tab_rows_expand_filter_and_start_chat(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run([sys.executable, str(root / "tests" / "_projects_probe.py"), str(root), data],
                                  cwd=root, capture_output=True, text=True, timeout=180, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("projects tab", "one row per project", "row shows counts and folder", "no full path shown",
                     "expanded shows tasks topics chats repos decisions", "filter by column",
                     "task start chat opens its task chat", "cli picked", "task chat has no draft",
                     "topic start chat opens the topic with the context as a draft",
                     "project start chat opens its topic", "no cli started", "reads throttled", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
