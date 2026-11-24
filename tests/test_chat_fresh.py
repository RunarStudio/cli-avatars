"""FIX.CHAT: on a fresh install (no topics) the docked chat shows its composer and Enter runs Claude.

The Tk window runs in a child process (``_chat_fresh_probe.py``), with a fake CLI.
"""

import os
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_room_pane
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FreshChatProbeTest(unittest.TestCase):
    def test_docked_chat_runs_claude_with_no_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_chat_fresh_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=90, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
