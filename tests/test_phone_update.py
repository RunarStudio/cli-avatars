"""PHONE.4: Update app from the phone. The cases run in a child (``_phone_update_cases``): they import tkinter."""

import subprocess  # noqa: TID251  # update_ui imports tkinter, so the cases run in a child, like test_update_button
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ("test_version_commit_and_last_check", "test_missing_tool_is_the_reason", "test_source_checkout_is_the_reason",
         "test_same_start_update_as_the_toolbar", "test_staged_quits_for_the_helper",
         "test_helper_not_started_is_a_failure", "test_updated", "test_rolled_back", "test_status_route",
         "test_start_needs_cookie_and_csrf", "test_start_once_then_refused_while_running",
         "test_blocked_reason_refused", "test_stopped_server_drops_kept_alive_phones", "test_progress_over_sse",
         "test_start_refused_with_writes_off")


class PhoneUpdate(unittest.TestCase):
    def test_cases_in_a_child(self):
        proc = subprocess.run([sys.executable, "-m", "unittest", "-v", "tests._phone_update_cases"],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in CASES:
            self.assertRegex(proc.stderr, rf"{name} \(.*\) \.\.\. ok")


if __name__ == "__main__":
    unittest.main()
