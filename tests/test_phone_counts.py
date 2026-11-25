"""DOOR-COUNTS on the phone: a counts badge per room on the map and in Rooms, a totals line, live over SSE."""

import http.client
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_webui import PROJECT, _Live  # noqa: E402

from cli_avatars.app.door_counts import KEYS  # noqa: E402
from cli_avatars.app.session_rooms import APOTHECARY  # noqa: E402
from decisions import ask_decision  # noqa: E402
from webui import auth, live, scene  # noqa: E402
from webui.demo import SESSIONS  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneCounts(_Live):
    def setUp(self):
        super().setUp()
        self.sessions = []
        live.set_sessions(lambda: list(self.sessions))
        self.addCleanup(live.set_sessions, None)

    def scene(self):
        resp, data = self.request("/api/scene")
        self.assertEqual(resp.status, 200)
        return json.loads(data)

    def test_every_room_has_counts_and_the_scene_has_totals(self):
        body = self.scene()
        for room in body["rooms"]:
            self.assertEqual(set(room["counts"]), set(KEYS), room["name"])
        self.assertEqual(set(body["counts"]), {"total", "projects"})
        self.assertEqual(body["counts"]["total"]["orchestrators"], 0)
        self.assertEqual(body["counts"]["total"]["open_topics"], 2)
        self.assertEqual(body["counts"]["projects"][PROJECT]["conversations"], 2)

    def test_sessions_and_decisions_count_in_their_room(self):
        self.sessions[:] = SESSIONS
        ask_decision(self.dir, agent="claude:mf01", room="moon-forge", question="Oak or ash?",
                     options=["a=oak", "b=ash"])
        rooms = {r["name"]: r["counts"] for r in self.scene()["rooms"]}
        self.assertEqual(rooms["moon-forge"]["orchestrators"], 1)
        self.assertEqual(rooms["moon-forge"]["decisions"], 1)
        self.assertEqual(rooms["glass-orchard"]["orchestrators"], 1)
        self.assertEqual(rooms[APOTHECARY]["decisions"], 0)

    def test_sse_pushes_counts_when_a_session_comes(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        resp.fp.readline()
        time.sleep(0.2)
        self.sessions[:] = SESSIONS[:1]
        deadline, seen = time.time() + 4, b""
        while time.time() < deadline and b"event: counts" not in seen:
            seen += resp.fp.readline()
        data = resp.fp.readline()
        conn.close()
        self.assertIn(b"event: counts", seen)
        body = json.loads(data.split(b"data: ", 1)[1])
        self.assertEqual(body["total"]["orchestrators"], 1)
        self.assertEqual(body["rooms"]["moon-forge"]["orchestrators"], 1)

    def test_counts_hold_no_ids_or_paths(self):
        self.sessions[:] = SESSIONS
        text = json.dumps(scene.counts_now(self.dir))
        for row in SESSIONS:
            self.assertNotIn(row["agent_id"], text)
        self.assertNotIn("/", text)


class Page(unittest.TestCase):
    def test_the_page_draws_counts(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="totals"', html)
        self.assertIn("function drawCounts(", js)
        self.assertIn('src.addEventListener("counts"', js)
        self.assertIn("paintTotals(", js)


if __name__ == "__main__":
    unittest.main()
