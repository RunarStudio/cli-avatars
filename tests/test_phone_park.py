"""PARK.1 + IDLE-PROPS.1 on the phone: the park, the idle objects, the task tables and who idles where, read-only."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app import park  # noqa: E402
from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import live, scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhonePark(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        for topic, kind in (("moon-forge", MAIN), ("glass-orchard", SIMPLE)):
            set_topic(self.dir, topic, title=topic, project="lantern", status="open")
            SessionRooms(self.dir / "ui" / "session_rooms.json").open(kind, "claude", topic)
        reg = Registry(self.dir)
        for title, column in (("Polish the lens", "doing"), ("Sort the seeds", "todo"), ("Mend the gate", "todo")):
            card = reg.task_create("lantern", title, topic="glass-orchard")
            if column != "todo":
                reg.task_move(card["id"], column)
        self.rows = [
            {"id": "a1b2c3d4", "kind": "orchestrator", "name": "Orrin", "room": park.NAME, "feet": (3.0, -9.0),
             "face": 1, "walk": False, "idle": {"act": "lift", "oid": "park:rack", "tier": "long"}},
            {"id": "e5f6a7b8", "kind": "orchestrator", "name": "Vessa", "room": "glass-orchard", "feet": (20.0, 0.0),
             "face": 1, "walk": False, "idle": {"act": "<b>dance</b>"}},
            {"id": "__you__", "kind": "user", "name": "You", "room": "Apothecary", "feet": (5.0, 4.0), "face": 1,
             "walk": False}]
        live.set_roster(lambda _lay, _now: self.rows)

    def tearDown(self):
        live.set_roster(None)
        super().tearDown()

    def test_the_scene_has_the_park_its_objects_and_the_tables(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        self.assertIn("park", {r["kind"] for r in body["rooms"]})
        found = body["park"]
        w, h = body["map"]["w"], body["map"]["h"]
        kinds = {p["kind"] for p in found["props"]}
        self.assertTrue({"hearth", "dice", "well"} <= kinds, kinds)
        for row in found["props"] + found["tables"]:
            x, y = row["at"]
            self.assertTrue(0 <= x < w and 0 <= y < h, row)
        tables = {t["room"]: t for t in found["tables"]}
        self.assertEqual(set(tables), {"moon-forge", "glass-orchard"})
        self.assertEqual(tables["glass-orchard"]["doing"], ["Polish the lens"])
        self.assertEqual(sorted(tables["glass-orchard"]["todo"]), ["Mend the gate", "Sort the seeds"])
        self.assertTrue(found["lamps"] and found["box"])

    def test_avatars_carry_a_known_idle_act_only(self):
        by = {a["name"]: a for a in scene.build_scene(self.dir)["avatars"]}
        self.assertEqual(by["Orrin"]["idle"], "lift")
        self.assertNotIn("idle", by["Vessa"])
        self.assertNotIn("idle", by["You"])
        self.assertEqual(scene.avatars_now(self.dir)[0]["idle"], "lift")

    def test_the_switches_take_the_park_and_the_objects_off(self):
        (self.dir / "config.json").write_text(json.dumps({"park": {"enabled": False},
                                                          "idle_props": {"enabled": False}}), encoding="utf-8")
        found = scene.build_scene(self.dir)
        self.assertNotIn("park", {r["kind"] for r in found["rooms"]})
        self.assertEqual((found["park"]["props"], found["park"]["lamps"]), ([], []))
        self.assertEqual(len(found["park"]["tables"]), 2)

    def test_the_page_draws_the_park(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/park.js", html)
        self.assertEqual(self.request("/static/park.js")[0], 200)
        js = (STATIC / "park.js").read_text(encoding="utf-8")
        for needle in ("function drawParkUnder(", "function drawParkLabels(", "scene.park", ".idle"):
            self.assertIn(needle, js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ("drawParkUnder(now)", "drawParkLabels()"):
            self.assertIn(needle, app)
        self.assertNotIn("innerHTML", js)


if __name__ == "__main__":
    unittest.main()
