"""TIMELAPSE on the phone: a read-only day of ghosts in map pixels, a chat opened at a moment, SSE for today."""

import http.client
import sys
import time
import unittest
import uuid
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board.store import LocalStore  # noqa: E402
from cli_avatars.app.session_rooms import SIMPLE, SessionRooms  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_daily_recap import at  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
TODAY = date.today()
DAY = TODAY - timedelta(days=1)


def epoch(day: date, hour: int, minute: int = 0) -> float:
    return datetime.combine(day, dtime(hour, minute)).timestamp()


class PhoneTimelapse(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        set_topic(self.dir, "moon-forge", title="Moon forge", project="lantern", status="open")
        set_topic(self.dir, "glass-orchard", title="Glass orchard", project="lantern", status="open")
        rooms = SessionRooms(self.dir / "ui" / "session_rooms.json")
        rooms.open(SIMPLE, "claude", "moon-forge")
        rooms.open(SIMPLE, "claude", "glass-orchard")
        reg = Registry(self.dir)
        gate = reg.task_create("lantern", "Polish the moon gate", topic="moon-forge")["id"]
        self.pear = reg.task_create("lantern", "Blow a glass pear", topic="glass-orchard")["id"]
        self.chat = f"task-{self.pear[:8]}-1"
        reg.store.update(self.pear, lambda c: ({**c, "chats": [{"id": str(uuid.uuid4()), "cli": "claude",
                                                               "created": at(DAY, 8), "room": self.chat}]}, []))
        store = LocalStore(self.dir)
        for hour, card in ((9, gate), (11, self.pear)):
            store.append_event({"id": str(uuid.uuid4()), "ts": at(DAY, hour), "card": card, "actor": "daniel",
                                "kind": "moved", "from": "todo", "to": "doing"})
        self.said = []
        for hour, sender, note in ((11, "user", "Blow it thin"), (12, "claude:room", "Blown"),
                                   (15, "claude:room", "Cooled")):
            ts = epoch(DAY, hour, 5)
            self.said.append(ts)
            append_channel(self.dir, {"ts": ts, "from": sender, "channel": self.chat, "icon": "speech",
                                      "to": "user" if sender != "user" else "claude:room", "note": note,
                                      "kind": "msg"})

    def test_a_day_of_ghosts_in_map_pixels(self):
        status, body = self.request(f"/api/timelapse?day={DAY.isoformat()}")
        self.assertEqual(status, 200)
        self.assertEqual((body["day"], body["label"], body["today"]), (DAY.isoformat(), "Yesterday", TODAY.isoformat()))
        self.assertEqual(body["first"], (TODAY - timedelta(days=29)).isoformat())
        you = next(a for a in body["avatars"] if a["name"] == "You")
        self.assertEqual((you["kind"], you["sprite"]), ("user", "user"))
        self.assertNotIn("daniel", str(body["avatars"]) + str(body["tracks"].keys()))
        self.assertIn("user", body["sprites"])
        steps = body["tracks"][you["id"]]
        self.assertEqual([s["m"] for s in steps][:2], [9 * 60, 11 * 60])
        w, h = body["map"]["w"], body["map"]["h"]
        for step in steps:
            self.assertTrue(0 <= step["at"][0] <= w and 0 <= step["at"][1] <= h, step)
        walk = steps[1]
        self.assertEqual((walk["span"], walk["route"][0], walk["route"][-1]), (6, steps[0]["at"], walk["at"]))
        self.assertGreater(len(walk["route"]), 2, "through the doors")
        self.assertEqual([m["chat"] for m in body["moments"]], [self.chat] * 3)
        self.assertEqual([m["ts"] for m in body["moments"]], self.said)
        self.assertTrue(all(m["aid"] in body["tracks"] for m in body["moments"]))
        self.assertNotIn("Blow it thin", str(body))
        self.assertIn(11 * 60, body["busy"])

    def test_bad_days_and_old_days(self):
        old = (TODAY - timedelta(days=40)).isoformat()
        self.assertEqual(self.request(f"/api/timelapse?day={old}")[1]["avatars"], [])
        self.assertEqual(self.request("/api/timelapse")[1]["day"], TODAY.isoformat())
        for bad in ("x", "2026-13-01", "../etc"):
            with self.subTest(bad=bad):
                self.assertEqual(self.request(f"/api/timelapse?day={bad}")[0], 400)

    def test_the_chat_opens_around_a_moment(self):
        status, body = self.request(f"/api/chat/{self.chat}?tail=2&around={self.said[0]}")
        self.assertEqual(status, 200)
        self.assertEqual([m["text"] for m in body["messages"]], ["Blow it thin", "Blown"])
        self.assertEqual([m["text"] for m in self.request(f"/api/chat/{self.chat}?tail=2")[1]["messages"]],
                         ["Blown", "Cooled"])
        self.assertEqual(self.request(f"/api/chat/{self.chat}?tail=2&around=x")[1]["messages"][-1]["text"], "Cooled")

    def test_unpaired_is_refused_and_writes_are_none(self):
        self.assertNotEqual(self.request("/api/timelapse", cookie=False)[0], 200)
        self.assertIn(self.request("/api/timelapse", "POST", {})[0], (404, 405))

    def test_the_page_has_the_time_lapse(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for needle in ('id="lapseBtn"', 'id="lapse"', 'id="lapseTrack"', "/static/timelapse.js",
                       "/static/timelapse.css"):
            self.assertIn(needle, html)
        for path in ("/static/timelapse.js", "/static/timelapse.css"):
            self.assertEqual(self.request(path)[0], 200, path)
        js = (STATIC / "timelapse.js").read_text(encoding="utf-8")
        for needle in ('"/api/timelapse', 'tone("tick")', 'tone("moment")', "state.focus.task", "showChat("):
            self.assertIn(needle, js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("timelapse"', app)
        self.assertIn("around=", app)

    def test_sse_carries_todays_new_frames(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        resp.fp.readline()
        time.sleep(0.2)
        append_channel(self.dir, {"ts": time.time(), "from": "user", "channel": self.chat, "icon": "speech",
                                  "to": "claude:room", "note": "Again", "kind": "msg"})
        seen, deadline = b"", time.time() + 4
        while time.time() < deadline and b"event: timelapse" not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b"event: timelapse", seen)


if __name__ == "__main__":
    unittest.main()
