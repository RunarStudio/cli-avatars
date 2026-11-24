"""ROOM-CHAT.4/.7: the chat pane with a fake CLI (no real CLI, network or key), and who may start a run.

The Tk pane runs in a child process (``_room_chat_probe.py``).
"""

import os
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_tasks_tab
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class BoundaryTest(unittest.TestCase):
    def test_working_dir_is_set_only_by_the_folder_dialog_handler(self):
        callers = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", ".git/", "build/")) or rel == "cli_avatars/model/room.py":
                continue
            if "set_working_dir(" in path.read_text(encoding="utf-8", errors="replace"):
                callers.append(rel)
        self.assertEqual(callers, ["cli_avatars/app/room_pane.py"])
        pane = (ROOT / "cli_avatars" / "app" / "room_pane.py").read_text(encoding="utf-8")
        self.assertEqual(pane.count("set_working_dir("), 1)
        self.assertIn("picked = self._ask_folder()", pane)

    def test_only_the_enter_handler_starts_a_run(self):
        text = (ROOT / "chat_window.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("from_ui_event("), 1)
        self.assertEqual(text.count("runner.start("), 1)
        self.assertEqual(text.count("self._send_cli("), 1)
        self.assertIn('entry.bind("<Return>", self._on_enter)', text)
        self.assertNotIn("shell=True", text)


class PaneProbeTest(unittest.TestCase):
    def test_pane_runs_two_turns_with_the_fake_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_room_chat_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=90, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok follow_up_resumes_session", result.stdout)
        self.assertIn("ok no_process_without_enter", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("done"), result.stdout)


if __name__ == "__main__":
    unittest.main()
