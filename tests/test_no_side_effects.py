"""The icacls-only Popen guard used by the MCP data tests."""

from __future__ import annotations

import shutil
import subprocess  # noqa: TID251  # CompletedProcess for the recorded icacls calls
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import events  # noqa: E402
from _no_side_effects import allowed_icacls, icacls_only  # noqa: E402


class Guard(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.sub = str(self.root / "projects")

    def test_known_icacls_shapes_on_our_dir_pass(self):
        for args in (
            ["icacls", self.sub, "/inheritance:r", "/grant:r", "DESKTOP\\some user:(OI)(CI)F"],
            ["icacls", self.sub, "/inheritance:r", "/grant:r", "someone:F"],
            ["icacls", self.sub],
            ["icacls", self.sub, "/reset"],
            ["icacls", str(self.root), "/remove", "BUILTIN\\Users"],
        ):
            with self.subTest(args=args):
                self.assertTrue(allowed_icacls(args, self.root))

    def test_anything_else_is_refused(self):
        outside = str(self.root.parent / "elsewhere")
        for args in (
            ["icacls", outside, "/reset"],
            ["icacls", self.sub, "/grant", "Everyone:F"],
            ["icacls", self.sub, "/inheritance:r", "/grant:r", "Everyone:R"],
            ["icacls", self.sub, "/remove", "/T"],
            ["icacls", self.sub, "/reset", "/T"],
            ["cmd", "/c", "icacls", self.sub],
            ["curl", "https://example.invalid"],
            "icacls " + self.sub,
            ["icacls"],
        ):
            with self.subTest(args=args):
                self.assertFalse(allowed_icacls(args, self.root))

    def test_popen_stand_in_refuses_shell_and_other_programs(self):
        popen = icacls_only(self.root)
        for call in (
            lambda: popen(["icacls", self.sub], shell=True),
            lambda: popen(["touch", str(self.root / "ran.txt")]),
            lambda: popen("icacls " + self.sub),
        ):
            with self.assertRaisesRegex(AssertionError, "network or process call"):
                call()
        self.assertFalse((self.root / "ran.txt").exists())

    def test_every_call_restrict_windows_makes_is_allowed(self):
        listing = (f"{self.sub} DESKTOP\\some user:(OI)(CI)(F)\n"
                   "           BUILTIN\\Users:(OI)(CI)(RX)\n\nSuccessfully processed 1 files").encode()
        calls = []

        def record(args):
            calls.append(["icacls", *args])
            return subprocess.CompletedProcess(args, 0, listing if len(args) == 1 else b"", b"")

        Path(self.sub).mkdir()
        with patch.object(events, "_windows_principal", return_value="DESKTOP\\some user"), \
                patch.object(events, "_run_icacls", record):
            events._restrict_windows(Path(self.sub))
        self.assertGreaterEqual(len(calls), 3)
        self.assertIn("/remove", [item for call in calls for item in call])
        for call in calls:
            with self.subTest(call=call):
                self.assertTrue(allowed_icacls(call, self.root))


if __name__ == "__main__":
    unittest.main()
