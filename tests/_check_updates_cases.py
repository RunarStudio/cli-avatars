"""Child cases for ``test_check_updates``: ``check_ui`` imports tkinter, which the suite process never loads.

CHECK-UPD.1: Check for updates from the toolbar, Settings, the tray and the phone. A fake ``check_dev`` and a fake
``run_update``, made-up commits; no git, no network.
"""

import http.client
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import focus
from cli_avatars.app import check_ui, cues, update_ui
from cli_avatars.update import progress
from cli_avatars.update.check import PHASE_CURRENT, PHASE_FAILED, PHASE_NEWS, CheckResult
from cli_avatars.update.machine import Toolchain, UpdateResult
from cli_avatars.update.version import STAMP_NAME, write_stamp
from webui import auth, server

OLD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
TOOLS = Toolchain("git", ("python",), True, "")
NEWS = CheckResult(PHASE_NEWS, "3 new on dev", 3, ("Map scroll unrolls", "Quieter torches", "Ember badge"), "f00d" * 10)


class _Root:
    def after(self, _ms, fn):
        fn()


class FakeCheck:
    """Stands in for ``check_dev``: says the fetch line, waits for the test, then answers ``result``."""

    def __init__(self, result=NEWS):
        self.result, self.calls, self.gate = result, [], threading.Event()

    def __call__(self, **kw):
        self.calls.append(kw)
        if kw.get("on_status"):
            kw["on_status"]("Check: checking dev")
        self.gate.wait(5)
        return self.result


class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="checkupd-ui-"))
        self.addCleanup(shutil.rmtree, self.base)
        self.data, self.install = self.base / "data", self.base / "CLI Avatars"
        self.data.mkdir()
        self.install.mkdir()
        write_stamp(self.install / STAMP_NAME, "1.2.0", OLD)
        self.fake = FakeCheck()
        self.updates, self.played = [], []
        self.app = SimpleNamespace(root=_Root(), config={}, _quit=lambda: None)
        patches = [mock.patch.object(update_ui, "installed_dir", lambda: self.install),
                   mock.patch.object(update_ui, "app_data_dir", lambda: self.data),
                   mock.patch.object(check_ui, "app_data_dir", lambda: self.data),
                   mock.patch.object(check_ui, "check_dev", self.fake),
                   mock.patch.object(update_ui, "run_update", self.update),
                   mock.patch.object(cues, "play", lambda _app, name: self.played.append(name)),
                   mock.patch.object(focus, "current", lambda _d: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        update_ui.apply_probe(self.app, TOOLS)
        self.phone = update_ui.PhoneUpdate(self.app, call=lambda fn: fn())

    def tearDown(self):
        self.fake.gate.set()

    def update(self, **kw):
        self.updates.append(kw)
        return UpdateResult(PHASE_CURRENT, "Already on dev", OLD, OLD, None, (), None)

    def wait(self, test, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if test():
                return True
            time.sleep(0.02)
        return False

    def finish(self):
        self.fake.gate.set()
        self.assertTrue(self.wait(lambda: not getattr(self.app, "_check_running", True)))


class CheckTests(_Base):
    def test_found_shows_count_subjects_badge_and_cue(self):
        self.assertEqual(check_ui.start_check(self.app), "")
        self.finish()
        self.assertRegex(self.app._update_line, r"^Check: 3 new on dev · checked \d\d:\d\d$")
        self.assertEqual(check_ui.badge_count(self.app), 3)
        self.assertEqual(self.played, ["found"])
        got = self.phone.status()["check"]
        self.assertEqual((got["phase"], got["behind"], got["subjects"][0]), (PHASE_NEWS, 3, "Map scroll unrolls"))
        self.assertRegex(got["at"], r"^\d\d:\d\d$")

    def test_up_to_date_has_no_badge_and_no_cue(self):
        self.fake.result = CheckResult(PHASE_CURRENT, "Up to date", upstream=OLD)
        check_ui.start_check(self.app)
        self.finish()
        self.assertRegex(self.app._update_line, r"^Check: up to date · checked \d\d:\d\d$")
        self.assertEqual(check_ui.badge_count(self.app), 0)
        self.assertEqual(self.played, [])

    def test_failure_is_the_reason_and_the_bar_stops_red_at_the_fetch(self):
        self.fake.result = CheckResult(PHASE_FAILED, "git fetch failed")
        check_ui.start_check(self.app)
        self.finish()
        self.assertEqual(self.app._update_line, "Check: git fetch failed")
        got = self.phone.status()
        self.assertEqual((got["tone"], got["pct"]), ("bad", progress.step("checking dev")[0]))

    def test_bar_is_only_the_fetch_phase_with_the_glint(self):
        check_ui.start_check(self.app)
        self.assertTrue(self.wait(lambda: self.fake.calls))
        got = self.phone.status()
        self.assertEqual((got["pct"], got["tone"], got["shimmer"]), (progress.step("checking dev")[0], "busy", True))
        self.assertTrue(got["check"]["running"])
        self.finish()
        self.assertEqual(self.phone.status()["tone"], "idle")

    def test_cue_held_while_a_task_is_in_focus(self):
        with mock.patch.object(focus, "current", lambda _d: "a-task-in-focus"):
            check_ui.start_check(self.app)
            self.finish()
        self.assertEqual(self.played, [])

    def test_missing_git_blocks_the_check(self):
        update_ui.apply_probe(self.app, Toolchain(None, ("python",), True, "git is not on PATH"))
        self.assertEqual(check_ui.start_check(self.app), "git is not on PATH")
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.phone.status()["check"]["enabled"])

    def test_missing_pyinstaller_does_not_block_the_check(self):
        update_ui.apply_probe(self.app, Toolchain("git", ("python",), False, "PyInstaller is not installed"))
        self.assertEqual(check_ui.start_check(self.app), "")
        self.finish()

    def test_from_source_checks_the_source_clone(self):
        with mock.patch.object(update_ui, "installed_dir", lambda: None):
            update_ui.apply_probe(self.app, TOOLS)
            self.assertEqual(check_ui.start_check(self.app), "")
            self.finish()
        self.assertIsNone(self.fake.calls[0]["install_dir"])
        self.assertTrue((Path(self.fake.calls[0]["source_root"]) / "cli_avatars").is_dir())

    def test_update_is_refused_while_checking(self):
        check_ui.start_check(self.app)
        self.assertTrue(self.wait(lambda: self.fake.calls))
        why = update_ui.start_update(self.app)
        self.assertIn("check", why.lower())
        self.assertEqual(self.updates, [])
        self.assertFalse(self.phone.status()["enabled"])
        self.finish()

    def test_check_is_refused_while_updating(self):
        self.app._update_running = True
        why = check_ui.start_check(self.app)
        self.assertIn("update", why.lower())
        self.assertEqual(self.fake.calls, [])
        self.app._update_running = False

    def test_check_once_at_a_time(self):
        self.assertEqual(check_ui.start_check(self.app), "")
        self.assertIn("already", check_ui.start_check(self.app))
        self.finish()
        self.assertEqual(len(self.fake.calls), 1)

    def test_an_update_that_finds_dev_current_clears_the_badge(self):
        check_ui.start_check(self.app)
        self.finish()
        self.assertEqual(update_ui.start_update(self.app), "")
        self.assertTrue(self.wait(lambda: not getattr(self.app, "_update_running", True)))
        self.assertEqual(check_ui.badge_count(self.app), 0)


class Tray(_Base):
    def test_tray_has_check_for_updates(self):
        items = []
        fake = ModuleType("pystray")
        fake.MenuItem = lambda text, action, **kw: items.append((text, action, kw)) or (text, action, kw)
        fake.Menu = lambda *a: a
        fake.Menu.SEPARATOR = "-"
        fake.Icon = lambda *a, **kw: SimpleNamespace(run=lambda: None)
        from cli_avatars.desktop import tray

        self.app._show_hud_win = self.app._update_app = lambda: None
        self.app.desktop_escape = False
        with mock.patch.dict(sys.modules, {"pystray": fake}), mock.patch.object(tray, "HAS_PIL", True):
            tray.setup_tray(self.app)
        found = [i for i in items if i[0] == "Check for updates"]
        self.assertEqual(len(found), 1, [i[0] for i in items])
        self.assertTrue(found[0][2]["enabled"](None))
        found[0][1](None, None)
        self.finish()
        self.assertEqual(len(self.fake.calls), 1)


class ServerTests(_Base):
    writes = False

    def setUp(self):
        super().setUp()
        self.token = auth.load_token(self.data)
        self.httpd = server.make_server(self.data, host="127.0.0.1", port=0, poll=0.05,
                                        writes=lambda: self.writes, updater=self.phone)
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

    def test_check_runs_with_writes_off(self):
        status, got = self.request("/api/update/check", "POST")
        self.assertEqual(status, 202, got)
        self.finish()
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.request("/api/update")[1]["check"]["behind"], 3)

    def test_check_needs_cookie_and_csrf(self):
        self.assertEqual(self.request("/api/update/check", "POST", cookie=False)[0], 401)
        self.assertEqual(self.request("/api/update/check", "POST", csrf=False)[0], 403)
        self.assertEqual(self.fake.calls, [])

    def test_update_itself_stays_behind_writes(self):
        self.assertEqual(self.request("/api/update", "POST")[0], 405)
        self.assertEqual(self.updates, [])

    def test_status_gives_the_phone_its_csrf(self):
        status, got = self.request("/api/update")
        self.assertEqual((status, got["csrf"]), (200, auth.csrf_value(self.token)))

    def test_refused_while_updating(self):
        self.app._update_running = True
        status, got = self.request("/api/update/check", "POST")
        self.assertEqual(status, 409)
        self.assertIn("update", got["why"].lower())
        self.app._update_running = False

    def test_without_the_app_the_phone_says_why(self):
        self.httpd.updater = server.NoUpdate()
        status, got = self.request("/api/update/check", "POST")
        self.assertEqual((status, got["why"]), (409, server.NoUpdate.CHECK_REASON))
        self.assertFalse(self.request("/api/update")[1]["check"]["enabled"])


if __name__ == "__main__":
    unittest.main()
