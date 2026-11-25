"""NEEDS-YOU.1 on the phone: the list is read always; with writes on, a tap clears one item (CSRF as PHONE.2)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import needs_you  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from webui import scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneNeedsYou(_Writes):
    def setUp(self):
        super().setUp()
        reg = Registry(self.dir)
        self.card = reg.task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        reg.task_move(self.card, "doing")
        reg.task_move(self.card, "blocked")
        append_channel(self.dir, {"ts": time.time() - 60, "from": "claude:room", "to": "user", "channel": "lantern",
                                  "icon": "speech", "note": "The glass is clear.", "kind": "msg"})

    def test_the_list_in_urgency_order(self):
        status, body = self.request("/api/needs-you")
        self.assertEqual((status, body["count"]), (200, 2))
        got = [(i["kind"], i["key"], i["title"]) for i in body["items"]]
        self.assertEqual(got, [("blocked", f"card:{self.card}", "Polish the lantern glass"),
                               ("reply", "room:lantern", "Lantern")])
        self.assertEqual(body["items"][1]["detail"], "The glass is clear.")
        self.assertEqual(set(body["items"][0]), {"key", "kind", "ts", "title", "detail", "room", "card"})

    def test_a_tap_clears_one_item_and_the_page_hears_it(self):
        before = scene.stamp(self.dir)
        status, body = self.request("/api/needs-you/clear", "POST", {"key": "room:lantern"})
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual([i["key"] for i in self.request("/api/needs-you")[1]["items"]], [f"card:{self.card}"])
        self.assertEqual([i["key"] for i in needs_you.pending(self.dir)], [f"card:{self.card}"])
        self.assertNotEqual(before, scene.stamp(self.dir))

    def test_bad_clears(self):
        for body in ({}, {"key": 5}, {"key": "../x"}, {"key": "room:lantern", "x": 1}):
            with self.subTest(body=body):
                self.assertEqual(self.request("/api/needs-you/clear", "POST", body)[0], 400)
        self.assertEqual(self.request("/api/needs-you/clear", "POST", {"key": "room:forge"})[0], 404)
        self.assertEqual(self.request("/api/needs-you/clear", "POST", {"key": "room:lantern"}, csrf=False)[0], 403)
        self.assertEqual(self.request("/api/needs-you")[1]["count"], 2)

    def test_the_page_has_the_sheet_and_the_badge(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ('id="needsBtn"', 'id="needsCount"', 'id="needs"', 'id="needsRows"'):
            self.assertIn(needle, html)
        self.assertIn('"/api/needs-you"', js)
        self.assertIn('"/api/needs-you/clear"', js)


class PhoneNeedsYouOff(_Writes):
    writes = False

    def test_reading_works_and_clearing_is_off(self):
        self.assertEqual(self.request("/api/needs-you")[0], 200)
        self.assertEqual(self.request("/api/needs-you/clear", "POST", {"key": "room:lantern"})[0], 405)


if __name__ == "__main__":
    unittest.main()
