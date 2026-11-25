"""MESSENGER on the phone: the courier walks the map as a roster row, a lit card carries its ribbon, read-only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import messenger  # noqa: E402
from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import live, scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneCourier(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        for topic, kind in (("moon-forge", MAIN), ("glass-orchard", SIMPLE)):
            set_topic(self.dir, topic, title=topic, project="lantern", status="open")
            SessionRooms(self.dir / "ui" / "session_rooms.json").open(kind, "claude", topic)
        reg = Registry(self.dir)
        self.forge = reg.task_create("lantern", "Forge the moon lantern", topic="moon-forge")
        self.orchard = reg.task_create("lantern", "Glass apple orchard", topic="glass-orchard")
        row = ask_decision(self.dir, agent="orrin", room="moon-forge", question="Silver or gold rims?",
                           options=["a=Silver", "b=Gold"], card=self.forge["id"])
        reg.decision_answer(row["id"], choice="a", text="affects Glass apple orchard")
        self.key = messenger.sync(self.dir)[0]["key"]
        self.rows = [
            {"id": "a1b2c3d4", "kind": "orchestrator", "name": "Orrin", "room": "moon-forge", "feet": (3.0, -9.0),
             "face": 1, "walk": False},
            {"id": f"courier:{self.key}", "kind": "courier", "name": "Courier", "room": "moon-forge",
             "feet": (6.0, -6.0), "face": -1, "walk": True}]
        live.set_roster(lambda _lay, _now: self.rows)

    def tearDown(self):
        live.set_roster(None)
        super().tearDown()

    def test_the_courier_walks_the_map_with_its_own_sprite(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        walker = next(a for a in body["avatars"] if a["kind"] == "courier")
        self.assertEqual((walker["sprite"], walker["walk"], walker["face"]), ("courier", True, -1))
        self.assertNotIn(self.key, str(body["avatars"]))
        self.assertIn("courier", body["sprites"])
        self.assertEqual(self.request("/api/sprite/courier.png")[0], 200)
        png, w, h, frames = scene.sprite_png("courier")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual((w, h, frames), (22, 30, 6))

    def test_sse_avatars_carry_the_walk(self):
        self.assertIn("courier", [a["kind"] for a in scene.avatars_now(self.dir)])
        self.rows.pop()
        self.assertNotIn("courier", [a["kind"] for a in scene.avatars_now(self.dir)])

    def test_nothing_glows_before_arrival(self):
        self.assertEqual(scene.build_scene(self.dir)["couriers"], [])
        self.assertNotIn("courier", {k for c in scene.cards(self.dir) for k in c})

    def test_an_arrived_courier_lights_the_card_and_the_room(self):
        before = scene.stamp(self.dir)
        messenger.mark(self.dir, self.key, messenger.ARRIVED)
        self.assertNotEqual(scene.stamp(self.dir), before)
        lit = scene.build_scene(self.dir)["couriers"]
        self.assertEqual([(c["room"], c["from"], c["card"]) for c in lit],
                         [("glass-orchard", "moon-forge", self.orchard["id"])])
        card = next(c for c in scene.cards(self.dir) if c["id"] == self.orchard["id"])
        self.assertEqual(card["courier"]["from"], "moon-forge")
        self.assertEqual(card["courier"]["question"], "Silver or gold rims?")
        self.assertIn("affects", card["courier"]["reason"])
        messenger.mark(self.dir, self.key, messenger.OPENED)
        self.assertEqual(scene.build_scene(self.dir)["couriers"], [])

    def test_the_page_draws_the_ribbon_and_the_glow(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for path in ("/static/courier.js", "/static/courier.css"):
            self.assertIn(path, html)
            self.assertEqual(self.request(path)[0], 200)
        js = (STATIC / "courier.js").read_text(encoding="utf-8")
        for needle in ("function courierMark(", "function drawCourierOver(", "NEW FROM ", "state.scene.couriers"):
            self.assertIn(needle, js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("drawCourierOver(now)", app)
        self.assertEqual(app.count("courierMark(li, c)"), 2)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("postJSON", js)


if __name__ == "__main__":
    unittest.main()
