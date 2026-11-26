"""PHONEFIX: an Update line that lands while the SSE stream is still opening reaches the phone."""

import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from webui import auth, scene, server


class _Updater(server.NoUpdate):
    """A made-up Update whose line the test moves by hand."""

    def __init__(self):
        self.n, self.line = 0, ""

    def seq(self) -> int:
        return self.n

    def status(self) -> dict:
        return {"line": self.line}

    def bump(self, line):
        self.line, self.n = line, self.n + 1


class UpdateDuringStreamOpen(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.updater = _Updater()
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05, updater=self.updater)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def test_line_between_retry_and_loop_is_sent(self):
        bumped, stamp = threading.Event(), scene.stamp

        def held_stamp(directory):
            bumped.wait(5)
            return stamp(directory)

        with mock.patch.object(scene, "stamp", held_stamp):
            conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=3)
            self.addCleanup(conn.close)
            token = auth.load_token(self.dir)
            conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(token)}"})
            resp = conn.getresponse()
            self.assertTrue(resp.fp.readline().startswith(b"retry:"))
            self.updater.bump("Update: pulling")
            bumped.set()
            seen = b""
            try:
                while b"Update: pulling" not in seen:
                    line = resp.fp.readline()
                    if not line:
                        break
                    seen += line
            except TimeoutError:
                pass
        self.assertIn(b"Update: pulling", seen)


if __name__ == "__main__":
    unittest.main()
