"""Update processes open no console window on Windows."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli_avatars.update import proc
from cli_avatars.update.helper import perform

subprocess = proc.subprocess

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0


class _StartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = 1


def _as_windows():
    """Patch the proc module to behave as on Windows, with the win32 subprocess constants."""
    patches = [
        mock.patch.object(proc.sys, "platform", "win32"),
        mock.patch.object(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW, create=True),
        mock.patch.object(subprocess, "DETACHED_PROCESS", DETACHED_PROCESS, create=True),
        mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP, create=True),
        mock.patch.object(subprocess, "STARTF_USESHOWWINDOW", STARTF_USESHOWWINDOW, create=True),
        mock.patch.object(subprocess, "SW_HIDE", SW_HIDE, create=True),
        mock.patch.object(subprocess, "STARTUPINFO", _StartupInfo, create=True),
    ]
    for patch in patches:
        patch.start()
    return patches


class TestUpdateWindowless(unittest.TestCase):
    def setUp(self):
        self.patches = _as_windows()
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "update.log"

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def _assert_no_window(self, kwargs):
        flags = kwargs.get("creationflags", 0)
        self.assertTrue(flags & CREATE_NO_WINDOW, "CREATE_NO_WINDOW missing")
        self.assertFalse(flags & DETACHED_PROCESS, "DETACHED_PROCESS makes Windows ignore CREATE_NO_WINDOW")
        self.assertIs(kwargs.get("shell"), False)

    def test_run_fixed_hides_console_child(self):
        done = subprocess.CompletedProcess([], 0, b"ok")
        with mock.patch.object(proc.subprocess, "run", return_value=done) as run:
            result = proc.run_fixed(["git", "fetch", "origin", "dev"], cwd=None, timeout_s=5, log_path=self.log)
        self.assertEqual(result.code, 0)
        kwargs = run.call_args.kwargs
        self._assert_no_window(kwargs)
        info = kwargs.get("startupinfo")
        self.assertIsNotNone(info, "hidden STARTUPINFO missing")
        self.assertTrue(info.dwFlags & STARTF_USESHOWWINDOW)
        self.assertEqual(info.wShowWindow, SW_HIDE)
        self.assertEqual(kwargs["timeout"], 5.0)
        self.assertIn("ok", self.log.read_text(encoding="utf-8"))

    def test_spawn_detached_is_windowless(self):
        with mock.patch.object(proc.subprocess, "Popen") as popen:
            proc.spawn_detached(["py", "-3", "-m", "cli_avatars.update.helper"], cwd=None)
        kwargs = popen.call_args.kwargs
        self._assert_no_window(kwargs)
        self.assertTrue(kwargs["creationflags"] & CREATE_NEW_PROCESS_GROUP)
        self.assertNotIn("startupinfo", kwargs, "the relaunched app must show its window")

    def test_helper_bootcheck_and_relaunch_are_windowless(self):
        base = Path(self.tmp.name)
        install, staging, data = base / "app", base / "app.staging", base / "data"
        for folder in (install, staging, data):
            folder.mkdir()
        (install / "cli-avatars.exe").write_bytes(b"old")
        (staging / "cli-avatars.exe").write_bytes(b"new")
        done = subprocess.CompletedProcess([], 0, b"")
        with mock.patch.object(proc.subprocess, "run", return_value=done) as run, \
                mock.patch.object(proc.subprocess, "Popen") as popen:
            outcome = perform(install, staging, data, "cli-avatars.exe", self.log)
        self.assertEqual(outcome, "relaunched")
        self.assertTrue(run.called)
        for call in run.call_args_list:
            self._assert_no_window(call.kwargs)
            self.assertIsNotNone(call.kwargs.get("startupinfo"))
        self._assert_no_window(popen.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
