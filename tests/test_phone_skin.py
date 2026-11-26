"""PHONESKIN: an open phone sheet owns every touch; the map and page behind stay still; wide unchanged (headless Chrome)."""

import json
import os
import shutil
import subprocess  # noqa: TID251  # the probe runs in a node child, fixed argv
import tempfile
import threading
import unittest
from pathlib import Path

from webui import auth, live, server
from webui.demo import seed

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def _playwright() -> bool:
    if not NODE:
        return False
    found = subprocess.run([NODE, "-e", "require.resolve('playwright')"], capture_output=True, timeout=20)
    return found.returncode == 0


@unittest.skipUnless(_playwright(), "node with playwright on NODE_PATH not found")
class PhoneSkin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        data = Path(cls._tmp.name)
        seed(data)
        live.set_roster(lambda lay, _now: [dict(r, walk=False) for r in live.fallback(lay, 0.0)])
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}"
            out = subprocess.run([NODE, str(ROOT / "tools" / "probe_phone_skin.js"), url, "360", "400", "1366"],
                                 capture_output=True, text=True, timeout=180, check=True, env=os.environ.copy())
            cls.widths = {w["width"]: w for w in json.loads(out.stdout)}
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
            live.set_roster(None)
            cls._tmp.cleanup()

    def picker(self, width):
        got = self.widths[width]
        p = got["picker"]
        self.assertTrue(p["mapInert"], "the map behind the picker takes no touch")
        self.assertTrue(p["locked"], "the page behind the picker does not scroll")
        self.assertGreater(p["bodyScroll"], 0, "a swipe on the sheet scrolls the sheet")
        self.assertGreater(p["stripScroll"], 0, "a swipe on the skins scrolls the skins")
        self.assertTrue(p["viewKept"], "the map view stays while the sheet is open")
        self.assertEqual(p["scrollAfter"], 0)
        self.assertTrue(got["heldDrag"], "a map drag in flight stops when the picker opens")
        pick = got["pick"]
        self.assertTrue(pick and pick["onTop"], pick)
        self.assertEqual(pick["got"], pick["skin"])
        self.assertEqual(pick["checked"], "true")
        self.assertEqual(got["saved"]["skin"], pick["skin"])
        self.assertFalse(got["closed"]["mapInert"] or got["closed"]["locked"], "closed: the map takes touches again")

    def every_sheet(self, width):
        got = self.widths[width]
        self.assertTrue(got["drawer"]["viewAfterSwipe"], "a swipe on the room drawer leaves the map")
        self.assertFalse(got["drawer"]["mapInert"], "the room drawer keeps the map live above it")
        for row in got["overlays"]:
            self.assertTrue(row["mapInert"] and row["locked"] and row["onTop"] and not row["selfInert"] and row["freed"], row)
        for row in got["openers"]:
            self.assertTrue(row["mapInert"] and row["locked"] and row["freed"], row)

    def test_picker_at_360(self):
        self.picker(360)

    def test_picker_at_400(self):
        self.picker(400)

    def test_every_sheet_at_360(self):
        self.every_sheet(360)

    def test_every_sheet_at_400(self):
        self.every_sheet(400)

    def test_wide_unchanged(self):
        got = self.widths[1366]
        pick = got["pick"]
        self.assertTrue(pick and pick["onTop"], pick)
        self.assertEqual(got["saved"]["skin"], pick["skin"])
        rows = [got["picker"], *got["overlays"], *got["openers"]]
        self.assertFalse([r for r in rows if r["mapInert"] or r["locked"]], "wide sheets stay as they were")


if __name__ == "__main__":
    unittest.main()
