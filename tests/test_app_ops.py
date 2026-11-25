"""OPS.1: ``cli-avatars-emit app status|restart|update|logs`` manage the running Dungeon over the loopback UDP channel.

A fake app answers (no Tk, no window, no real restart, no git). Nothing here starts an AI CLI.
"""

import json
import os
import socket
import subprocess  # noqa: TID251  # the CLI runs as a child, as an agent would run it
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli_avatars_emit
import emit_app
import events
from cli_avatars.app import ops
from events import EventBus, EventSource, load_or_create_token

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Root:
    """Runs ``after`` callbacks at once, on the caller's thread."""

    def after(self, _ms, fn):
        fn()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name) / "data"
        self.data.mkdir()
        self.token = load_or_create_token(self.data)
        self.spawned, self.quit, self.updates = [], [], []
        self.update_why = ""
        self.app = SimpleNamespace(root=_Root(), config={}, _update_running=False, _update_line="",
                                   _quit=lambda: self.quit.append(1), _ops_started=time.time() - 75)
        self.source = None

    def tearDown(self):
        if self.source is not None:
            self.source.close()
        events.close_logging()
        self._tmp.cleanup()

    def start_update(self, app):
        self.updates.append(app)
        return self.update_why

    def listen(self) -> int:
        self.source = EventSource(EventBus(), port=0, data_dir=self.data, token=self.token)
        control = ops.Control(self.app, directory=self.data, call=lambda fn: fn(), start_update=self.start_update,
                              spawn=lambda argv, cwd: self.spawned.append(list(argv)))
        self.source.on_control = control.handle
        return self.source.port

    def cli(self, *argv, port=None):
        """The CLI as a child process, the way a Claude or Grok session runs it."""
        env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(self.data))
        cmd = [sys.executable, "-m", "cli_avatars_emit", "app", *argv, "--port", str(port or _free_port())]
        return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, shell=False)

    def run_main(self, *argv, port=None):
        """The CLI in this process, so ``spawn_detached`` can be replaced."""
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_avatars_emit.main(["app", *argv, "--port", str(port or _free_port()),
                                          "--data-dir", str(self.data)])
        return code, out.getvalue(), err.getvalue()


class StatusTests(_Base):
    def test_not_running_exits_3_with_running_false(self):
        proc = self.cli("status", "--json")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertIs(got["running"], False)
        self.assertEqual(got["data_dir"], str(self.data))

    def test_not_running_plain_is_one_line(self):
        proc = self.cli("status")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stdout.strip().splitlines(), ["CLI Avatars: not running"])

    def test_running_reports_version_uptime_phone_and_data_dir(self):
        port = self.listen()
        proc = self.cli("status", "--json", port=port)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertIs(got["running"], True)
        self.assertEqual(got["pid"], os.getpid())
        self.assertTrue(got["version"])
        self.assertIn("commit", got)
        self.assertGreaterEqual(got["uptime_s"], 75)
        self.assertEqual(got["phone"], {"on": False, "writes": False})
        self.assertEqual(got["data_dir"], str(self.data))
        self.assertEqual(got["update"], {"running": False, "line": ""})
        self.assertNotIn(self.token, proc.stdout)
        self.assertNotIn(str(Path.home()), proc.stdout.replace(str(self.data), ""))

    def test_phone_on_and_writes_on(self):
        self.app._phone_server = object()
        self.app.config = {"web": {"enabled": True, "allow_writes": True}}
        got = ops.status(self.app, self.data)
        self.assertEqual(got["phone"], {"on": True, "writes": True})

    def test_plain_status_names_uptime(self):
        port = self.listen()
        proc = self.cli("status", port=port)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CLI Avatars: running", proc.stdout)
        self.assertIn("up 1m", proc.stdout)

    def test_wrong_token_gets_no_answer(self):
        port = self.listen()
        self.source.token = "x" * 32
        proc = self.cli("status", "--json", port=port)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(self.source.stats["rejected_auth"], 1)

    def test_control_is_not_published_on_the_bus(self):
        seen = []
        self.listen()
        self.source.bus.subscribe(seen.append)
        packet = json.dumps({"type": "control", "token": self.token, "verb": "status", "id": "abc"}).encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(2)
            self.assertTrue(self.source.handle_datagram(packet, sock.getsockname()))
            reply = json.loads(sock.recv(65535))
        self.assertEqual((reply["id"], reply["running"]), ("abc", True))
        self.assertEqual(seen, [])

    def test_a_gone_asker_does_not_stop_the_listener(self):
        port = self.listen()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            gone = sock.getsockname()
        self.source.handle_datagram(json.dumps({"type": "control", "token": self.token, "verb": "status"}).encode(),
                                    gone)
        self.assertEqual(self.cli("status", "--json", port=port).returncode, 0)

    def test_unknown_verb_is_rejected(self):
        with self.assertRaises(events.EventRejected):
            events.parse_packet({"type": "control", "token": self.token, "verb": "shell"}, self.token)


class RestartTests(_Base):
    def test_restart_running_relaunches_and_quits(self):
        port = self.listen()
        proc = self.cli("restart", "--wait", "0", port=port)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Restarting", proc.stdout)
        self.assertEqual(self.quit, [1])
        self.assertEqual(len(self.spawned), 1)
        argv = self.spawned[0]
        self.assertEqual(argv[-2:], ["--wait-pid", str(os.getpid())])
        self.assertEqual(argv[:-2], ops.launch_argv())
        self.assertFalse({"claude", "grok"} & {Path(item).stem.lower() for item in argv})

    def test_restart_refused_while_update_runs(self):
        self.app._update_running = True
        port = self.listen()
        proc = self.cli("restart", "--wait", "0", port=port)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)
        self.assertIn("Update", proc.stderr)
        self.assertEqual((self.quit, self.spawned), ([], []))

    def test_restart_logs_to_the_app_log(self):
        ops.restart(self.app, self.data, spawn=lambda argv, cwd: None)
        self.assertIn("restart", (self.data / ops.APP_LOG).read_text(encoding="utf-8"))

    def test_not_running_starts_the_recorded_app(self):
        exe = Path(self._tmp.name) / "CLI Avatars" / "cli-avatars"
        exe.parent.mkdir()
        exe.write_text("", encoding="utf-8")
        ops.write_app_json(self.data, [str(exe)])
        spawned = []
        with mock.patch.object(emit_app, "spawn_detached", lambda argv, cwd: spawned.append((list(argv), cwd))):
            code, out, _err = self.run_main("restart", "--wait", "0")
        self.assertEqual(code, 0)
        self.assertIn("Starting", out)
        self.assertEqual(spawned, [([str(exe)], exe.parent)])

    def test_not_running_ignores_a_foreign_recorded_argv(self):
        ops.write_app_json(self.data, ["/bin/sh", "-c", "echo pwned"])
        spawned = []
        with mock.patch.object(emit_app, "spawn_detached", lambda argv, cwd: spawned.append(list(argv))):
            code, _out, _err = self.run_main("restart", "--wait", "0")
        self.assertEqual(code, 0)
        self.assertEqual(spawned, [[sys.executable, str(ROOT / "overlay.py")]])

    def test_wait_for_exit_of_a_gone_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"], shell=False)
        proc.wait(10)
        start = time.monotonic()
        self.assertTrue(ops.wait_for_exit(proc.pid, timeout=5))
        self.assertLess(time.monotonic() - start, 2)

    def test_wait_for_exit_times_out_on_a_live_process(self):
        self.assertFalse(ops.wait_for_exit(os.getppid(), timeout=0.3))


class UpdateTests(_Base):
    def test_update_calls_the_update_button_path(self):
        port = self.listen()
        proc = self.cli("update", port=port)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.updates, [self.app])
        self.assertIn("Update started", proc.stdout)

    def test_update_refused_names_the_reason(self):
        self.update_why = "Update: already running"
        port = self.listen()
        proc = self.cli("update", port=port)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr.strip(), "Update: already running")

    def test_update_not_running_is_one_line(self):
        proc = self.cli("update")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)
        self.assertIn("not running", proc.stderr)


class LogsTests(_Base):
    def test_tail_prints_the_last_lines(self):
        for n in range(5):
            ops.log_line(self.data, f"line {n}")
        proc = self.cli("logs", "--tail", "2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("line 3") and lines[1].endswith("line 4"))

    def test_update_log(self):
        (self.data / "update.log").write_text("---- git fetch origin dev\n---- exit 0\n", encoding="utf-8")
        proc = self.cli("logs", "--log", "update", "--tail", "1")
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "---- exit 0"))

    def test_missing_log_is_one_line(self):
        proc = self.cli("logs")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
