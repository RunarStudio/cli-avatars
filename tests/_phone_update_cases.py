"""Child cases for ``test_phone_update``: ``update_ui`` imports tkinter, which the suite process never loads.

PHONE.4: Update app from the phone. Same ``start_update`` as the toolbar; a fake updater, made-up commits.
No git, no PyInstaller, no helper: ``run_update`` and ``spawn_detached`` are replaced in ``update_ui``.
"""

import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cli_avatars.app import update_ui
from cli_avatars.update.machine import PHASE_CURRENT, PHASE_STAGED, STATE_NAME, Toolchain, UpdateResult
from cli_avatars.update.version import STAMP_NAME, write_stamp
from webui import auth, server

OLD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
NEW = "f00dfacec0ffee1234567890abcdef1234567890"
TOOLS = Toolchain("git", ("python",), True, "")


class _Root:
    """Runs ``after`` callbacks at once, on the caller's thread."""

    def after(self, _ms, fn):
        fn()


class FakeUpdater:
    """Stands in for ``run_update``: two progress lines, waits for the test, then decides."""

    def __init__(self, phase=PHASE_CURRENT):
        self.phase, self.calls, self.gate = phase, [], threading.Event()

    def __call__(self, **kw):
        self.calls.append(kw)
        kw["on_status"]("Update: checking dev")
        kw["on_status"]("Update: pulling")
        self.gate.wait(5)
        if self.phase == PHASE_STAGED:
            return UpdateResult(PHASE_STAGED, "Restarting onto the new build", OLD, NEW, Path("s"),
                                ("python", "-m", "cli_avatars.update.helper"), Path("."))
        return UpdateResult(PHASE_CURRENT, "Already on dev", OLD, OLD, None, (), None)


class _Base(unittest.TestCase):
    commit = OLD
    block = ""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.data, self.install = base / "data", base / "CLI Avatars"
        self.data.mkdir()
        self.install.mkdir()
        write_stamp(self.install / STAMP_NAME, "1.2.0", self.commit)
        self.fake = FakeUpdater()
        self.spawned, self.quit = [], []
        self.app = SimpleNamespace(root=_Root(), config={}, _update_block=self.block, _update_toolchain=TOOLS,
                                   _quit=lambda: self.quit.append(1))
        patches = [mock.patch.object(update_ui, "installed_dir", lambda: self.install),
                   mock.patch.object(update_ui, "app_data_dir", lambda: self.data),
                   mock.patch.object(update_ui, "run_update", self.fake),
                   mock.patch.object(update_ui, "spawn_detached", lambda argv, cwd: self.spawned.append(argv))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.updater = update_ui.PhoneUpdate(self.app, call=lambda fn: fn())

    def tearDown(self):
        self.fake.gate.set()
        self._tmp.cleanup()

    def wait(self, test, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if test():
                return True
            time.sleep(0.02)
        return False


class StatusTests(_Base):
    def test_version_commit_and_last_check(self):
        (self.data / STATE_NAME).write_text(json.dumps({"last_checked": "2026-11-24 21:05", "phase": "up_to_date",
                                                        "commit": OLD[:12], "upstream": OLD[:12]}))
        got = self.updater.status()
        self.assertEqual(got["commit"], OLD[:12])
        self.assertEqual(got["channel"], "dev")
        self.assertEqual(got["last_checked"], "2026-11-24 21:05")
        self.assertTrue(got["version"])
        self.assertTrue(got["enabled"])
        self.assertEqual(got["reason"], "")
        self.assertFalse(got["running"])

    def test_missing_tool_is_the_reason(self):
        update_ui.apply_probe(self.app, Toolchain(None, (), False, "git is not on PATH"))
        got = self.updater.status()
        self.assertFalse(got["enabled"])
        self.assertEqual(got["reason"], "git is not on PATH")

    def test_source_checkout_is_the_reason(self):
        with mock.patch.object(update_ui, "installed_dir", lambda: None):
            update_ui.apply_probe(self.app, TOOLS)
            got = self.updater.status()
        self.assertFalse(got["enabled"])
        self.assertTrue(got["reason"].startswith("Running from source"), got["reason"])
        self.assertEqual(self.updater.start(), got["reason"])
        self.assertEqual(self.fake.calls, [])

    def test_same_start_update_as_the_toolbar(self):
        with mock.patch.object(update_ui, "start_update", wraps=update_ui.start_update) as start:
            self.assertEqual(self.updater.start(), "")
            start.assert_called_once_with(self.app)
        self.fake.gate.set()
        self.assertTrue(self.wait(lambda: not self.updater.status()["running"]))
        self.assertEqual(self.updater.status()["phase"], PHASE_CURRENT)

    def test_staged_quits_for_the_helper(self):
        self.fake.phase = PHASE_STAGED
        self.fake.gate.set()
        self.assertEqual(self.updater.start(), "")
        self.assertTrue(self.wait(lambda: self.quit))
        self.assertEqual(self.spawned, [("python", "-m", "cli_avatars.update.helper")])
        self.assertEqual(self.updater.status()["phase"], PHASE_STAGED)


    def test_helper_not_started_is_a_failure(self):
        self.fake.phase = PHASE_STAGED
        self.fake.gate.set()

        def refuse(argv, cwd):
            raise OSError("no helper")

        with mock.patch.object(update_ui, "spawn_detached", refuse):
            self.assertEqual(self.updater.start(), "")
            self.assertTrue(self.wait(lambda: not self.updater.status()["running"]))
        got = self.updater.status()
        self.assertEqual((got["phase"], got["note"]), ("failed", "could not start the restart helper"))
        self.assertEqual(self.quit, [])

class RelaunchTests(_Base):
    """A fresh process reads the last record: the helper relaunched the new build, or rolled back."""

    commit = NEW

    def staged(self):
        (self.data / STATE_NAME).write_text(json.dumps({"last_checked": "2026-11-24 21:05", "phase": "staged",
                                                        "commit": OLD[:12], "upstream": NEW[:12]}))

    def test_updated(self):
        self.staged()
        got = self.updater.status()
        self.assertEqual(got["phase"], "updated")
        self.assertIn(NEW[:12], got["note"])

    def test_rolled_back(self):
        self.staged()
        write_stamp(self.install / STAMP_NAME, "1.2.0", OLD)
        got = self.updater.status()
        self.assertEqual(got["phase"], "rolled_back")
        self.assertIn(OLD[:12], got["note"])


class ServerTests(_Base):

    def setUp(self):
        super().setUp()
        self.token = auth.load_token(self.data)
        self.httpd = server.make_server(self.data, host="127.0.0.1", port=0, poll=0.05,
                                        writes=lambda: True, updater=self.updater)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.fake.gate.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        super().tearDown()

    def request(self, path, method="GET", csrf=True, cookie=True):
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        if cookie:
            headers["Cookie"] = f"{auth.COOKIE}={auth.session_value(self.token)}"
        if csrf:
            headers["X-CLI-Avatars-CSRF"] = auth.csrf_value(self.token)
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data or b"{}")

    def test_status_route(self):
        self.assertEqual(self.request("/api/update", cookie=False)[0], 401)
        status, got = self.request("/api/update")
        self.assertEqual(status, 200)
        self.assertEqual(got["commit"], OLD[:12])
        self.assertTrue(got["enabled"])

    def test_start_needs_cookie_and_csrf(self):
        self.assertEqual(self.request("/api/update", "POST", cookie=False)[0], 401)
        self.assertEqual(self.request("/api/update", "POST", csrf=False)[0], 403)
        self.assertEqual(self.fake.calls, [])

    def test_start_once_then_refused_while_running(self):
        status, got = self.request("/api/update", "POST")
        self.assertEqual(status, 202, got)
        self.assertTrue(self.wait(lambda: self.fake.calls))
        status, got = self.request("/api/update", "POST")
        self.assertEqual(status, 409)
        self.assertIn("already running", got["why"])
        self.fake.gate.set()
        self.assertTrue(self.wait(lambda: not self.updater.status()["running"]))
        self.assertEqual(len(self.fake.calls), 1)

    def test_blocked_reason_refused(self):
        update_ui.apply_probe(self.app, Toolchain(None, (), False, "git is not on PATH"))
        status, got = self.request("/api/update", "POST")
        self.assertEqual((status, got.get("why")), (409, "git is not on PATH"))
        self.assertEqual(self.fake.calls, [])

    def test_stopped_server_drops_kept_alive_phones(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        cookie = {"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"}
        conn.request("GET", "/api/update", headers=cookie)
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 200)
        self.httpd.shutdown()
        conn.request("GET", "/api/update", headers=cookie)
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 503)
        self.assertEqual(resp.getheader("Connection"), "close")

    def test_progress_over_sse(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        self.assertTrue(resp.fp.readline().startswith(b"retry:"))
        self.assertEqual(self.request("/api/update", "POST")[0], 202)
        seen = b""
        deadline = time.time() + 4
        while time.time() < deadline and b"Update: pulling" not in seen:
            seen += resp.fp.readline()
        self.fake.gate.set()
        while time.time() < deadline and b'"phase":"up_to_date"' not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b"event: update", seen)
        self.assertIn(b"Update: pulling", seen)
        self.assertIn(b'"phase":"up_to_date"', seen)


class WritesOffTests(_Base):
    def test_start_refused_with_writes_off(self):
        token = auth.load_token(self.data)
        httpd = server.make_server(self.data, host="127.0.0.1", port=0, poll=0.05, writes=lambda: False,
                                   updater=self.updater)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            conn.request("POST", "/api/update", body=b"{}", headers={
                "Content-Type": "application/json", "Cookie": f"{auth.COOKIE}={auth.session_value(token)}",
                "X-CLI-Avatars-CSRF": auth.csrf_value(token)})
            self.assertEqual(conn.getresponse().status, 405)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
