"""BODY on the phone: each avatar's pose and its room's smoke ride the scene and the SSE avatars, read-only."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import live, scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneBody(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        for topic, kind in (("moon-forge", MAIN), ("glass-orchard", SIMPLE)):
            set_topic(self.dir, topic, title=topic, project="lantern", status="open")
            SessionRooms(self.dir / "ui" / "session_rooms.json").open(kind, "claude", topic)
        self.rows = [
            {"id": "a1b2c3d4", "kind": "orchestrator", "name": "Orrin", "room": "moon-forge", "feet": (3.0, -9.0),
             "face": 1, "walk": True, "pose": "stride", "smoke": 0.64},
            {"id": "e5f6a7b8", "kind": "orchestrator", "name": "Vessa", "room": "glass-orchard", "feet": (20.0, 0.0),
             "face": 1, "walk": False, "pose": "slump", "smoke": 7},
            {"id": "c9d0e1f2", "kind": "orchestrator", "name": "Pell", "room": "glass-orchard", "feet": (18.0, 1.0),
             "face": -1, "walk": False, "pose": "dance", "smoke": "thick"},
            {"id": "__you__", "kind": "user", "name": "You", "room": "Apothecary", "feet": (5.0, 4.0), "face": 1,
             "walk": False}]
        live.set_roster(lambda _lay, _now: self.rows)

    def tearDown(self):
        live.set_roster(None)
        super().tearDown()

    def test_avatars_carry_a_known_pose_and_a_clamped_smoke(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        by = {a["name"]: a for a in body["avatars"]}
        self.assertEqual((by["Orrin"]["pose"], by["Orrin"]["smoke"]), ("stride", 0.64))
        self.assertEqual((by["Vessa"]["pose"], by["Vessa"]["smoke"]), ("slump", 1.0))
        self.assertEqual((by["Pell"]["pose"], by["Pell"]["smoke"]), ("idle", 0.0))
        self.assertEqual((by["You"]["pose"], by["You"]["smoke"]), ("idle", 0.0))
        self.assertNotIn("a1b2c3d4", str(body["avatars"]))

    def test_rooms_say_where_smoke_rises(self):
        rooms = {r["name"]: r for r in scene.build_scene(self.dir)["rooms"]}
        forge, orchard = rooms["moon-forge"]["smoke"], rooms["glass-orchard"]["smoke"]
        self.assertFalse(forge["chimney"])
        self.assertTrue(orchard["chimney"])
        width, height = scene.build_scene(self.dir)["map"]["w"], scene.build_scene(self.dir)["map"]["h"]
        for spot in (forge, orchard):
            x, y = spot["at"]
            self.assertTrue(0 <= x < width and 0 <= y < height, spot)

    def test_sse_avatars_carry_the_pose(self):
        self.assertEqual(scene.avatars_now(self.dir)[1]["pose"], "slump")
        self.rows[1] = {**self.rows[1], "pose": "idle"}
        time.sleep(0.01)
        self.assertEqual(scene.avatars_now(self.dir)[1]["pose"], "idle")

    def test_the_page_draws_the_poses(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/body.js", html)
        self.assertEqual(self.request("/static/body.js")[0], 200)
        js = (STATIC / "body.js").read_text(encoding="utf-8")
        for needle in ("function drawPosed(", "function drawBodyUnder(", "function drawBodyOver(", '"slump"',
                       '"stride"', '"tap"', "room.smoke"):
            self.assertIn(needle, js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ("drawPosed(a, sheet, meta, f, walking, top, now)", "drawBodyUnder(now)", "drawBodyOver(now)"):
            self.assertIn(needle, app)
        self.assertNotIn("innerHTML", js)


if __name__ == "__main__":
    unittest.main()
