"""PHONE.2: the phone map shows the Apothecary with its roamers and every avatar, moving over SSE."""

import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms
from webui import auth, live, server
from webui.scene import build_scene


def _inside(poly, x, y):
    hit = False
    j = len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


ROAMERS = [
    {"id": "claude:ab12", "kind": "orchestrator", "name": "Claude-ab12"},
    {"id": "bot:night-owl", "kind": "grok", "name": "Night owl"},
    {"id": "claude:ab12/sub1", "kind": "subagent", "name": "helper"},
]


class _Dir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        live.set_roster(None)
        self._tmp.cleanup()


class ApothecaryTests(_Dir):
    def test_apothecary_alone_has_the_user_roaming_it(self):
        scene = build_scene(self.dir)
        self.assertEqual([r["name"] for r in scene["rooms"]], ["Apothecary"])
        apothecary = scene["rooms"][0]
        mine = [a for a in scene["avatars"] if a["room"] == "Apothecary"]
        self.assertEqual([a["kind"] for a in mine], ["user"])
        self.assertTrue(_inside(apothecary["poly"], *mine[0]["at"]), mine[0])
        self.assertIn(mine[0]["sprite"], scene["sprites"])

    def test_every_roster_avatar_shows_roamers_too(self):
        rooms = SessionRooms(self.dir / "ui" / "session_rooms.json")
        self.assertEqual(rooms.open(MAIN, "claude", "moon-forge"), "")
        self.assertEqual(rooms.open(SIMPLE, "grok", "glass-orchard"), "")
        live.set_roster(lambda lay, now: live.fallback(lay, now, ROAMERS))
        scene = build_scene(self.dir)
        polys = {r["name"]: r["poly"] for r in scene["rooms"]}
        by_id = {a["id"]: a for a in scene["avatars"]}
        self.assertEqual(len(by_id), len(scene["avatars"]))
        kinds = sorted(a["kind"] for a in scene["avatars"])
        self.assertEqual(kinds, ["grok", "grok", "orchestrator", "orchestrator", "subagent", "user"])
        roamers = [a for a in scene["avatars"] if a["room"] == "Apothecary"]
        self.assertEqual(len(roamers), 4)
        for avatar in scene["avatars"]:
            self.assertTrue(_inside(polys[avatar["room"]], *avatar["at"]), avatar)
            self.assertIn(avatar["sprite"], scene["sprites"])
            self.assertNotIn(":", avatar["id"])

    def test_live_roster_from_the_dungeon_wins(self):
        live.set_roster(lambda lay, now: [{"id": "x1", "kind": "orchestrator", "name": "Live one",
                                           "room": "Apothecary", "feet": (5.0, 4.0), "face": -1, "walk": True}])
        scene = build_scene(self.dir)
        self.assertEqual([a["name"] for a in scene["avatars"]], ["Live one"])
        self.assertEqual(scene["avatars"][0]["face"], -1)
        self.assertTrue(scene["avatars"][0]["walk"])


class SpriteTests(_Dir):
    def test_roster_looks_serve_idle_and_walk_rows(self):
        from webui.scene import sprite_png

        for key in ("user", "orchestrator", "grok", "subagent", "grok-200"):
            strip = sprite_png(key)
            self.assertIsNotNone(strip, key)
            png, side, _h, frames = strip
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertEqual(side, 40 if key != "subagent" else 32)
            self.assertGreaterEqual(frames, 2)
        self.assertIsNone(sprite_png("grok-999"))
        self.assertIsNone(sprite_png("grok-x"))


class AvatarStreamTests(_Dir):
    def test_sse_sends_avatar_positions_that_move(self):
        start = time.monotonic()
        live.set_roster(lambda lay, now: [{"id": "w1", "kind": "orchestrator", "name": "Walker",
                                           "room": "Apothecary", "feet": (2.0 + (time.monotonic() - start), 3.0),
                                           "face": 1, "walk": True}])
        token = auth.load_token(self.dir)
        httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(token)}"})
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            seen, deadline = [], time.time() + 5
            event = None
            while time.time() < deadline and len(seen) < 2:
                line = resp.fp.readline().decode("utf-8").strip()
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event == "avatars":
                    seen.append(json.loads(line[6:]))
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
        self.assertEqual(len(seen), 2, seen)
        self.assertEqual(seen[0]["avatars"][0]["name"], "Walker")
        self.assertNotEqual(seen[0]["avatars"][0]["at"], seen[1]["avatars"][0]["at"])


class HallSnapshotTests(unittest.TestCase):
    def test_hall_publishes_feet_for_the_phone(self):
        from types import SimpleNamespace

        from cli_avatars.app.inside_roster import roster_rows
        from cli_avatars.model.agent import AgentInfo

        agents = {"claude:ab12": AgentInfo("claude:ab12", "Claude-ab12", source="claude"),
                  "bot:owl": AgentInfo("bot:owl", "Owl", source="bot")}
        inside = {aid: SimpleNamespace(agent=a, dir=1) for aid, a in agents.items()}
        feet = {"claude:ab12": (3.0, 2.0), "bot:owl": (4.0, 5.0), "__you__": (5.0, 4.0)}
        rows = roster_rows(feet, inside, {"claude:ab12": "Apothecary", "bot:owl": "Apothecary",
                                          "__you__": "Apothecary"}, {}, set())
        kinds = {r["id"]: r["kind"] for r in rows}
        self.assertEqual(kinds, {"claude:ab12": "orchestrator", "bot:owl": "grok", "__you__": "user"})
        self.assertEqual(next(r for r in rows if r["id"] == "__you__")["name"], "You")


if __name__ == "__main__":
    unittest.main()


class DungeonRosterTests(unittest.TestCase):
    def test_fresh_snapshot_is_used_and_a_stale_one_falls_back(self):
        from types import SimpleNamespace

        from webui.phone_ui import dungeon_roster

        rows = [{"id": "__you__", "kind": "user", "name": "You", "room": "Apothecary", "feet": (1.0, 1.0)}]
        app = SimpleNamespace(places=SimpleNamespace(_hall=SimpleNamespace(snapshot=(time.monotonic(), rows))))
        self.assertEqual(dungeon_roster(app), rows)
        app.places._hall.snapshot = (time.monotonic() - 10, rows)
        self.assertIsNone(dungeon_roster(app))
        self.assertIsNone(dungeon_roster(SimpleNamespace()))
