"""BUG-CONSOLE: agent CLI starts and the tailscale check open no console window on Windows."""

import unittest
from pathlib import Path
from unittest import mock

import emit_phone
from cli_avatars.runner import cli_runner

subprocess = cli_runner.subprocess

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
ARGV = ["claude", "-p", "--output-format", "stream-json"]


def _platform(name):
    """Patch both modules' platform and the win32 subprocess constants."""
    patches = [
        mock.patch.object(cli_runner.sys, "platform", name),
        mock.patch.object(cli_runner.os, "name", "nt" if name == "win32" else "posix"),
        mock.patch.object(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW, create=True),
        mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP, create=True),
    ]
    for patch in patches:
        patch.start()
    return patches


class TestNoConsole(unittest.TestCase):
    def _spawn(self, name):
        patches = _platform(name)
        try:
            with mock.patch.object(subprocess, "Popen") as popen, \
                    mock.patch.object(cli_runner, "_assign_job_object"), \
                    mock.patch.object(cli_runner, "_remember_group"):
                argv = list(ARGV)
                cli_runner._popen(argv, Path("."), {})
        finally:
            for patch in reversed(patches):
                patch.stop()
        return popen.call_args.kwargs

    def _tailscale(self, name):
        patches = _platform(name)
        try:
            with mock.patch.object(emit_phone.subprocess, "run") as run:
                emit_phone._tailscale("tailscale", "serve", "status", "--json")
        finally:
            for patch in reversed(patches):
                patch.stop()
        return run.call_args

    def test_windows_cli_spawn_hides_console_and_keeps_group(self):
        kwargs = self._spawn("win32")
        self.assertTrue(kwargs["creationflags"] & CREATE_NO_WINDOW, "CREATE_NO_WINDOW missing")
        self.assertTrue(kwargs["creationflags"] & CREATE_NEW_PROCESS_GROUP, "Stop needs the process group")
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["args"], ARGV)
        self.assertNotIn("start_new_session", kwargs)

    def test_posix_cli_spawn_unchanged(self):
        for name in ("linux", "darwin"):
            kwargs = self._spawn(name)
            self.assertEqual(kwargs.get("creationflags", 0), 0)
            self.assertIs(kwargs["start_new_session"], True)
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(kwargs["args"], ARGV)

    def test_windows_tailscale_hides_console(self):
        call = self._tailscale("win32")
        self.assertTrue(call.kwargs.get("creationflags", 0) & CREATE_NO_WINDOW, "CREATE_NO_WINDOW missing")
        self.assertIs(call.kwargs["shell"], False)
        self.assertEqual(call.args[0], ["tailscale", "serve", "status", "--json"])

    def test_posix_tailscale_has_no_flags(self):
        for name in ("linux", "darwin"):
            call = self._tailscale(name)
            self.assertEqual(call.kwargs.get("creationflags", 0), 0)
            self.assertIs(call.kwargs["shell"], False)


if __name__ == "__main__":
    unittest.main()
