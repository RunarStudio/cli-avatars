"""GROK-ORCH.1 desktop: New chat start and resume, the main orchestrator setting and Ask a bot, off-screen in a child."""

import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_projects_desktop
import sys
import tempfile
import unittest
from pathlib import Path


class Desktop(unittest.TestCase):
    def test_start_resume_switch_ask_a_bot_and_pages(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            data, work = Path(tmp) / "data", Path(tmp) / "work"
            data.mkdir()
            proc = subprocess.run([sys.executable, str(root / "tests" / "_grok_orch_probe.py"), str(root), str(data),
                                   str(work)], cwd=root, capture_output=True, text=True, timeout=180, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("quick grok chat starts with nothing picked", "chat list shows it with resume", "reopen picks its cli",
                     "switch saves config.json", "switch is live", "send writes the hand-off file", "two asks open at once",
                     "answer lands", "answer cue plays", "slip shows answered and the answer", "answer in the task's chat",
                     "pages show the next action first", "the rest is folded", "more opens the rest",
                     "page kept as markdown", "nothing ran", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
