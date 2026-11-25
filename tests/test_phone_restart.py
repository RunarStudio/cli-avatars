"""OPS.1: Restart in the phone's App sheet. A fake updater stands in for the app; nothing restarts here."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from webui import auth, server


class PhoneRestartTests(unittest.TestCase):
    """The App sheet's Restart: writes on, paired, CSRF; the app's own restart; refused reasons are 409."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.token = auth.load_token(self.dir)
        self.why, self.calls, self.writes = "", [], True
        updater = server.NoUpdate()
        updater.restart = lambda: self.calls.append(1) or self.why
        self.httpd = server.make_server(self.dir, port=0, poll=0.05, writes=lambda: self.writes, updater=updater)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self._tmp.cleanup()

    def post(self, csrf=True):
        headers = {"Content-Type": "application/json", "Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"}
        if csrf:
            headers["X-CLI-Avatars-CSRF"] = auth.csrf_value(self.token)
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("POST", "/api/restart", body=b"{}", headers=headers)
        resp = conn.getresponse()
        body = json.loads(resp.read() or b"{}")
        conn.close()
        return resp.status, body

    def test_restart_202(self):
        self.assertEqual(self.post(), (202, {"ok": True}))
        self.assertEqual(self.calls, [1])

    def test_refused_reason_409(self):
        self.why = "Update is running. Restart after it finishes."
        self.assertEqual(self.post(), (409, {"why": self.why}))

    def test_needs_csrf(self):
        self.assertEqual(self.post(csrf=False)[0], 403)
        self.assertEqual(self.calls, [])

    def test_writes_off_refused(self):
        self.writes = False
        self.assertNotIn(self.post()[0], (200, 202))
        self.assertEqual(self.calls, [])

    def test_app_alone_names_why(self):
        self.assertTrue(server.NoUpdate().restart())



if __name__ == "__main__":
    unittest.main()
