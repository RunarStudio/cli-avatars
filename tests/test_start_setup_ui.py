"""START-SETUP.1: the start card, New chat, the To: line and the tour on a real Tk root, in a child process.

Made-up folders and a stub binary; PATH is an empty folder. Skips without a display.
"""

import os
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_summon
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ProbeTest(unittest.TestCase):
    def test_start_card_new_chat_to_line_and_tour(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty-path"
            empty.mkdir()
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"), PATH=str(empty))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_start_setup_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=180, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith("done"), result.stdout)


if __name__ == "__main__":
    unittest.main()
