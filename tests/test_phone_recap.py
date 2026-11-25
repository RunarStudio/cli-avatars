"""DAILY-RECAP on the phone: a read-only Recap page, same grouping as the desktop, live over SSE."""

import sys
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board.store import LocalStore  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_daily_recap import at  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
TODAY = date.today()


class PhoneRecap(_Writes):
    def setUp(self):
        super().setUp()
        self.card = Registry(self.dir).task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        LocalStore(self.dir).append_event({"id": str(uuid.uuid4()), "ts": at(TODAY - timedelta(days=1), 14),
                                           "card": self.card, "actor": "daniel", "kind": "moved",
                                           "from": "todo", "to": "doing"})

    def test_today_grouped_agent_then_task(self):
        status, body = self.request("/api/recap")
        self.assertEqual(status, 200)
        self.assertEqual((body["day"], body["label"]), (TODAY.isoformat(), "Today"))
        self.assertEqual([a["name"] for a in body["agents"]], ["You"])
        task = body["agents"][0]["tasks"][0]
        self.assertEqual((task["card"], task["title"], task["counts"]["created"]),
                         (self.card, "Polish the lantern glass", 1))
        self.assertIn("commits: none logged", task["lines"])
        self.assertEqual(body["first"], (TODAY - timedelta(days=29)).isoformat())

    def test_a_past_day_and_bad_days(self):
        day = (TODAY - timedelta(days=1)).isoformat()
        status, body = self.request(f"/api/recap?day={day}")
        self.assertEqual((status, body["label"]), (200, "Yesterday"))
        self.assertIn("moved todo → doing", body["agents"][0]["tasks"][0]["lines"][0])
        old = (TODAY - timedelta(days=40)).isoformat()
        self.assertEqual(self.request(f"/api/recap?day={old}")[1]["agents"], [])
        for bad in ("x", "2026-13-01", "../etc", "2026-1-1"):
            with self.subTest(bad=bad):
                self.assertEqual(self.request(f"/api/recap?day={bad}")[0], 400)

    def test_unpaired_is_refused_and_writes_are_none(self):
        self.assertNotEqual(self.request("/api/recap", cookie=False)[0], 200)
        self.assertIn(self.request("/api/recap", "POST", {})[0], (404, 405))

    def test_the_page_has_the_recap(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ('id="recapBtn"', 'id="recap"', 'id="recapRows"', 'id="recapPrev"', 'id="recapNext"',
                       'id="recapDay"'):
            self.assertIn(needle, html)
        self.assertIn('"/api/recap', js)
        self.assertIn("loadRecap()", js.split('src.addEventListener("change"', 1)[1].split("});", 1)[0])


class PhoneRecapReadOnly(_Writes):
    writes = False

    def test_reading_works_with_writes_off(self):
        self.assertEqual(self.request("/api/recap")[0], 200)


if __name__ == "__main__":
    unittest.main()
