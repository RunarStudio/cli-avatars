"""OPS.2: ``cli-avatars-emit app phone status|refresh`` check and redo ``tailscale serve`` for the phone view.

A stub ``tailscale`` on a temp PATH records its argv and answers from a state file; the real one never runs.
"""

import json
import os
import socket
import subprocess  # noqa: TID251  # the CLI runs as a child, as an agent would run it
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import events
from cli_avatars.app import ops
from events import EventBus, EventSource, load_or_create_token

ROOT = Path(__file__).resolve().parent.parent
HOST = "dungeon-pc.example-tailnet.ts.net"

STUB = '''import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
with open(here / "argv.log", "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
state = here / "serve.json"
args = sys.argv[1:]
if args[:2] == ["serve", "status"]:
    print(state.read_text() if state.exists() else "{}")
elif args[:2] == ["serve", "reset"]:
    state.unlink(missing_ok=True)
elif args[:2] == ["serve", "--bg"]:
    port = args[2]
    state.write_text(json.dumps({"TCP": {"443": {"HTTPS": True}}, "Web": {"%s:443": {"Handlers": {"/": {
        "Proxy": "http://127.0.0.1:" + port}}}}}))
    print("Available within your tailnet:\\n\\nhttps://%s/\\n|-- proxy http://127.0.0.1:" + port)
else:
    sys.exit(2)
''' % (HOST, HOST)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.data = base / "data"
        self.data.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        self.config = base / "config.json"
        ops.write_app_json(self.data, [sys.executable, str(ROOT / "overlay.py")], config=self.config)
        self.token = load_or_create_token(self.data)
        self.source = None

    def tearDown(self):
        if self.source is not None:
            self.source.close()
        events.close_logging()
        self._tmp.cleanup()

    def stub(self, serving_port=None):
        """Put the stub ``tailscale`` on the temp PATH, optionally already forwarding to ``serving_port``."""
        (self.bin / "tailscale_stub.py").write_text(STUB, encoding="utf-8")
        if sys.platform == "win32":
            (self.bin / "tailscale.cmd").write_text(
                f'@"{sys.executable}" "{self.bin / "tailscale_stub.py"}" %*\r\n', encoding="utf-8")
        else:
            script = self.bin / "tailscale"
            script.write_text(f"#!{sys.executable}\n" + STUB, encoding="utf-8")
            script.chmod(0o755)
        if serving_port is not None:
            (self.bin / "serve.json").write_text(json.dumps({"TCP": {"443": {"HTTPS": True}}, "Web": {
                f"{HOST}:443": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{serving_port}"}}}}}))

    def calls(self) -> list:
        log = self.bin / "argv.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def settings(self, **web):
        self.config.write_text(json.dumps({"chat": {"auto_notes": False}, "web": web}), encoding="utf-8")

    def saved(self) -> dict:
        return json.loads(self.config.read_text(encoding="utf-8"))

    def listen(self, serving=True) -> int:
        self.app = SimpleNamespace(root=None, config=json.loads(self.config.read_text(encoding="utf-8")),
                                   _config_path=self.config, _phone_server=object() if serving else None,
                                   _update_running=False, _update_line="", _ops_started=time.time())
        self.source = EventSource(EventBus(), port=0, data_dir=self.data, token=self.token)
        self.source.on_control = ops.Control(self.app, directory=self.data, call=lambda fn: fn()).handle
        return self.source.port

    def cli(self, *argv, port=None):
        env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(self.data), PATH=str(self.bin))
        cmd = [sys.executable, "-m", "cli_avatars_emit", "app", "phone", *argv, "--port", str(port or _free_port())]
        return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60, shell=False)


class PhoneStatusTests(_Base):
    def test_not_forwarding(self):
        self.stub()
        self.settings(enabled=True, port=47280)
        proc = self.cli("status", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertEqual((got["phone_view"], got["port"], got["listen"]), ("on", 47280, "127.0.0.1"))
        self.assertEqual((got["address"], got["serve"]), ("", "no"))
        self.assertEqual(self.calls(), [["serve", "status", "--json"]])

    def test_forwarding_names_the_https_address(self):
        self.stub(serving_port=47280)
        self.settings(enabled=True, port=47280, address=f"https://{HOST}")
        got = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((got["serve"], got["serve_address"]), ("yes", f"https://{HOST}"))

    def test_forwarding_another_port_is_no(self):
        self.stub(serving_port=47999)
        self.settings(enabled=True, port=47280)
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["serve"], "no")

    def test_tailscale_not_found(self):
        self.settings(enabled=True)
        proc = self.cli("status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Tailscale serve: tailscale not found", proc.stdout)

    def test_plain_lines(self):
        self.stub(serving_port=47280)
        self.settings(enabled=False, port=47280, address=f"https://{HOST}")
        out = self.cli("status").stdout
        self.assertIn("Phone view: off · port 47280 · listen 127.0.0.1", out)
        self.assertIn(f"Phone address: https://{HOST}", out)
        self.assertIn(f"Tailscale serve: yes, https://{HOST} -> 127.0.0.1:47280", out)

    def test_running_app_says_whether_it_serves(self):
        self.stub()
        self.settings(enabled=True)
        port = self.listen(serving=False)
        got = json.loads(self.cli("status", "--json", port=port).stdout)
        self.assertEqual((got["app"], got["phone_view"]), ("running", "off"))


class PhoneRefreshTests(_Base):
    def test_refresh_serves_saves_and_prints_the_address(self):
        self.stub()
        self.settings(enabled=True, port=47280)
        proc = self.cli("refresh")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), [["serve", "--bg", "47280"], ["serve", "status", "--json"]])
        self.assertEqual(proc.stdout.strip().splitlines()[-1], f"https://{HOST}")
        saved = self.saved()
        self.assertEqual(saved["web"]["address"], f"https://{HOST}")
        self.assertEqual(saved["chat"], {"auto_notes": False})
        self.assertIs(saved["web"]["enabled"], True)

    def test_unchanged_address_is_not_rewritten(self):
        self.stub(serving_port=47280)
        self.settings(enabled=True, port=47280, address=f"https://{HOST}")
        before = self.config.stat().st_mtime_ns
        proc = self.cli("refresh")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("saved", proc.stdout)
        self.assertEqual(self.config.stat().st_mtime_ns, before)

    def test_running_app_takes_the_new_address(self):
        self.stub()
        self.settings(enabled=True, port=47280)
        port = self.listen()
        proc = self.cli("refresh", port=port)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.app.config["web"]["address"], f"https://{HOST}")
        self.assertEqual(self.app.config["web"]["port"], 47280)

    def test_reset_runs_first_and_warns(self):
        self.stub(serving_port=47280)
        self.settings(enabled=True, port=47280)
        proc = self.cli("refresh", "--reset")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls()[:2], [["serve", "reset"], ["serve", "--bg", "47280"]])
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)
        self.assertIn("loses it", proc.stderr)

    def test_never_funnel_down_logout_or_up(self):
        self.stub()
        self.settings(enabled=True, port=47280)
        self.cli("refresh", "--reset")
        self.cli("status")
        words = {word for argv in self.calls() for word in argv}
        self.assertFalse(words & {"funnel", "down", "logout", "up", "login"})

    def _refused(self, proc, text):
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, proc.stderr)
        self.assertIn(text, proc.stderr)
        self.assertNotIn(["serve", "--bg", "47280"], self.calls())

    def test_refused_when_phone_view_off(self):
        self.stub()
        self.settings(enabled=False)
        self._refused(self.cli("refresh"), "Phone view is off")

    def test_refused_when_running_app_does_not_serve(self):
        self.stub()
        self.settings(enabled=True)
        self._refused(self.cli("refresh", port=self.listen(serving=False)), "Phone view is off")

    def test_refused_without_tailscale(self):
        self.settings(enabled=True)
        self._refused(self.cli("refresh"), "tailscale not found")

    def test_refused_when_not_loopback(self):
        self.stub()
        self.settings(enabled=True, bind="100.101.102.103")
        self._refused(self.cli("refresh"), "not Loopback")

    def test_reset_refused_states_run_nothing(self):
        self.stub()
        self.settings(enabled=False)
        self.cli("refresh", "--reset")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
