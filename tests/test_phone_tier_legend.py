"""BUGFIX: the map's tier legend is whole and uncovered at 360 and 400 px, and stays bottom-left on a wide screen."""

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
class TierLegend(unittest.TestCase):
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
            out = subprocess.run([NODE, str(ROOT / "tools" / "probe_tier_legend.js"), url, "360", "400", "1366"],
                                 capture_output=True, text=True, timeout=90, check=True, env=os.environ.copy())
            cls.widths = {w["width"]: w for w in json.loads(out.stdout)}
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
            cls._tmp.cleanup()

    def check(self, width):
        got = self.widths[width]
        canvas = got["canvas"]
        for row in got["rows"]:
            self.assertGreaterEqual(row["left"], canvas["left"], row)
            self.assertLessEqual(row["right"], canvas["right"], row)
            self.assertGreaterEqual(row["top"], canvas["top"], row)
            self.assertLessEqual(row["bottom"], canvas["bottom"], row)
            self.assertEqual(row["over"], [], row)

    def test_legend_whole_at_360(self):
        self.check(360)

    def test_legend_whole_at_400(self):
        self.check(400)

    def test_wide_legend_sits_at_the_bottom(self):
        self.check(1366)
        got = self.widths[1366]
        self.assertLessEqual(got["canvas"]["bottom"] - got["rows"][-1]["bottom"], 24, got)


if __name__ == "__main__":
    unittest.main()
