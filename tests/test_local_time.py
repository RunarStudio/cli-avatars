"""LEFTOVERS: every shown time is local, like the Grok topics strip; stored stamps stay UTC."""

import os
import subprocess  # noqa: TID251  # update_ui imports tkinter, so the Tk case runs in a child, like test_update_bar
import sys
import tempfile
import time
import unittest
from pathlib import Path

from cli_avatars.app.tasks_edit import chat_rows, history_lines

ROOT = Path(__file__).resolve().parent.parent
CARD = {"chats": [{"room": "task-lamp-grok", "cli": "grok", "created": "2026-11-27T10:05:00Z"}],
        "history": [{"ts": "2026-11-27T10:05:00Z", "kind": "moved", "actor": "daniel", "from": "todo", "to": "doing"},
                    {"ts": "2026-06-30T22:40:00Z", "kind": "commented", "actor": "daniel", "text": "Wick trimmed"}]}


class LocalTime(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Madrid"
        time.tzset()

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_history_lines_show_local_time(self):
        lines = history_lines(CARD)
        self.assertEqual(lines[0], "07-01 00:40 daniel: Wick trimmed")
        self.assertEqual(lines[1], "11-27 11:05 daniel moved todo → doing")

    def test_card_chats_show_local_start(self):
        with tempfile.TemporaryDirectory() as data:
            self.assertEqual(chat_rows(data, CARD)[0]["started"], "11-27 11:05")

    def test_update_last_checked_shows_local_time(self):
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_local_time_probe.py"), str(ROOT), data],
                                  cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
                                  env={**os.environ, "TZ": "Europe/Madrid"})
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertIn("ok update last checked in local time", proc.stdout, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
