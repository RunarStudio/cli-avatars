"""YOU-AVATAR on the phone: avatars carry their need, your avatar its badge; you.js draws them read-only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app.session_rooms import MAIN, SessionRooms  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import live  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneYou(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        set_topic(self.dir, "moon-forge", title="moon-forge", project="lantern", status="open")
        SessionRooms(self.dir / "ui" / "session_rooms.json").open(MAIN, "claude", "moon-forge")
        self.rows = [
            {"id": "a1b2c3d4", "kind": "orchestrator", "name": "Orrin", "room": "moon-forge", "feet": (3.0, -9.0),
             "face": 1, "walk": False, "need": "decision"},
            {"id": "e5f6a7b8", "kind": "orchestrator", "name": "Vessa", "room": "moon-forge", "feet": (4.0, -9.0),
             "face": 1, "walk": False, "need": "dance"},
            {"id": "__you__", "kind": "user", "name": "You", "room": "moon-forge", "feet": (5.0, -8.0), "face": 1,
             "walk": False, "badge": 1}]
        live.set_roster(lambda _lay, _now: self.rows)

    def tearDown(self):
        live.set_roster(None)
        super().tearDown()

    def test_needs_and_badge_ride_the_scene(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        by = {a["name"]: a for a in body["avatars"]}
        self.assertEqual(by["Orrin"]["need"], "decision")
        self.assertNotIn("need", by["Vessa"])
        self.assertEqual(by["You"]["badge"], 1)
        self.assertNotIn("badge", by["Orrin"])

    def test_no_badge_while_nothing_waits(self):
        self.rows[-1]["badge"] = 0
        by = {a["name"]: a for a in self.request("/api/scene")[1]["avatars"]}
        self.assertNotIn("badge", by["You"])

    def test_page_loads_you_js_read_only(self):
        html = self.request("/")[1] if isinstance(self.request("/")[1], str) else ""
        js = (STATIC / "you.js").read_text(encoding="utf-8")
        self.assertEqual(self.request("/static/you.js")[0], 200)
        self.assertIn("/static/you.js", (STATIC / "index.html").read_text(encoding="utf-8") + html)
        self.assertIn("drawYouOver", js)
        self.assertIn("drawYouOver", (STATIC / "app.js").read_text(encoding="utf-8"))
        for word in ("fetch(", "POST", "XMLHttpRequest"):
            self.assertNotIn(word, js)


if __name__ == "__main__":
    unittest.main()
