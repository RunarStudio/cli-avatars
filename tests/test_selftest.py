"""Headless smoke of overlay --selftest. Skips when Tk cannot open. BUILD-EXE."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tk_reason() -> str:
    probe = subprocess.run(
        [sys.executable, "-c", "import tkinter; root = tkinter.Tk(); root.withdraw(); root.destroy()"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return ""
    detail = (probe.stderr or probe.stdout).strip()
    return detail or "tkinter failed"


class SelftestTests(unittest.TestCase):
    def test_selftest_returns_zero(self):
        reason = _tk_reason()
        if reason:
            self.skipTest("Tk unavailable: " + reason)
        result = subprocess.run(
            [sys.executable, "overlay.py", "--selftest"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selftest: ok", result.stdout)
