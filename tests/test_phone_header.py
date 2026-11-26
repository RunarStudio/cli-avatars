"""PHONEFIX: every map-pane header control sits inside a 360 or 400 px phone and takes its own tap (headless Chrome)."""

import json
import os
import shutil
import subprocess  # noqa: TID251  # the probe runs in a node child, fixed argv
import tempfile
import threading
import unittest
from pathlib import Path

from webui import auth, server
from webui.demo import seed

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def _playwright() -> bool:
    if not NODE:
        return False
    found = subprocess.run([NODE, "-e", "require.resolve('playwright')"], capture_output=True, timeout=20)
    return found.returncode == 0


@unittest.skipUnless(_playwright(), "node with playwright on NODE_PATH not found")
class PhoneHeader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        data = Path(cls._tmp.name)
        seed(data)
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}"
            out = subprocess.run([NODE, str(ROOT / "tools" / "probe_phone_header.js"), url, "360", "400", "1366"],
                                 capture_output=True, text=True, timeout=90, check=True, env=os.environ.copy())
            cls.widths = {w["width"]: w for w in json.loads(out.stdout)}
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
            cls._tmp.cleanup()

    def check(self, width):
        got = self.widths[width]
        ids = {c["id"] for c in got["controls"]}
        self.assertGreaterEqual(len(ids), 10, got)
        if "fit" not in ids:
            self.assertTrue(got["home"]["hit"], got["home"])
        for c in got["controls"]:
            self.assertGreaterEqual(c["left"], 0, c)
            self.assertLessEqual(c["right"], width, c)
            self.assertGreaterEqual(c["right"] - c["left"], 28, c)
            self.assertTrue(c["hit"], c)

    def test_every_control_reachable_at_360(self):
        self.check(360)

    def test_every_control_reachable_at_400(self):
        self.check(400)

    def test_wide_header_is_one_row(self):
        got = self.widths[1366]["controls"]
        self.assertEqual(len({round(c["top"]) for c in got}), 1, got)
        self.assertIn("fit", {c["id"] for c in got})
        self.check(1366)


if __name__ == "__main__":
    unittest.main()
