"""PHONECLEAN: a calm phone map at 360 and 400 px and a way around it anyone finds; wide unchanged (headless Chrome)."""

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


def _overlap(a, b) -> bool:
    return a["left"] < b["right"] - 1 and b["left"] < a["right"] - 1 and a["top"] < b["bottom"] - 1 and b["top"] < a["bottom"] - 1


@unittest.skipUnless(_playwright(), "node with playwright on NODE_PATH not found")
class PhoneClean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        data = Path(cls._tmp.name)
        seed(data)
        # the demo's avatars stand still, so the idle redraw is the sprites' own pace
        live.set_roster(lambda lay, _now: [dict(r, walk=False) for r in live.fallback(lay, 0.0)])
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}"
            out = subprocess.run([NODE, str(ROOT / "tools" / "probe_phone_clean.js"), url, "360", "400", "1366"],
                                 capture_output=True, text=True, timeout=150, check=True, env=os.environ.copy())
            cls.widths = {w["width"]: w for w in json.loads(out.stdout)}
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
            live.set_roster(None)
            cls._tmp.cleanup()

    def calm(self, width):
        got = self.widths[width]
        self.assertTrue(any(m["kind"] == "label" for m in got["marks"]), got["marks"])
        self.assertFalse([m for m in got["marks"] if m["kind"] in ("counts", "legend")], "plaques and legend wait for zoom or tap")
        boxes = got["marks"] + got["tools"]
        clashes = [(a["kind"], b["kind"]) for i, a in enumerate(boxes) for b in boxes[i + 1:] if _overlap(a, b)]
        self.assertEqual(clashes, [], got)
        self.assertEqual(got["loops"], [], "no idle flicker")
        self.assertLessEqual(got["idle"], 28, "idle redraws at the sprites' pace, about 12 a second")
        self.assertAlmostEqual(got["scale"], round(got["scale"]), places=6)
        self.assertFalse(got["mini"], "the mini-map waits until the view is zoomed in")

    def finds_its_way(self, width):
        got = self.widths[width]
        for word in ("Drag", "Pinch", "double-tap", "Tap a room"):
            self.assertIn(word, got["hint"], got["hint"])
        self.assertEqual(got["legendInHint"], 4)
        self.assertEqual(got["rooms"].split()[-1], "Rooms")
        self.assertIn("map", got["full"].lower())
        z = got["zoom"]
        self.assertTrue(z["mapIn"] and z["mapOut"] and z["mapHelp"], z)
        self.assertAlmostEqual(z["inRatio"], 2, places=3)
        self.assertAlmostEqual(z["inScale"], round(z["inScale"]), places=6)
        self.assertTrue(z["miniIn"], z)
        self.assertAlmostEqual(z["outRatio"], 1, places=3)
        self.assertAlmostEqual(z["homeRatio"], 1, places=3)
        self.assertFalse(got["hintAfterReload"], "the hint shows once")
        self.assertTrue(got["hintAgain"], "? opens it again")

    def test_calm_at_360(self):
        self.calm(360)

    def test_calm_at_400(self):
        self.calm(400)

    def test_navigation_found_at_360(self):
        self.finds_its_way(360)

    def test_navigation_found_at_400(self):
        self.finds_its_way(400)

    def test_wide_unchanged(self):
        got = self.widths[1366]
        self.assertEqual(got["hint"], "")
        self.assertEqual(got["zoom"], {"mapIn": False, "mapOut": False, "mapHelp": False})
        self.assertEqual(len([m for m in got["marks"] if m["kind"] == "legend"]), 4)
        self.assertTrue(got["mini"])


if __name__ == "__main__":
    unittest.main()
