"""LEFTOVERS: a decision asked in a room (no card), open on the desktop's Needs you, is on the phone's Decisions sheet
too, and the phone can answer it."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from decisions import ask_decision, list_decisions  # noqa: E402
from needs_you import pending as needs  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402

ME = "a1b2c3d4"


class PhoneRoomDecisions(_Writes):
    def setUp(self):
        super().setUp()
        self.row = ask_decision(self.dir, agent=ME, room="lantern", question="Clear or smoked glass?",
                                options=["a=Clear", "b=Smoked"])

    def test_a_room_decision_is_on_the_phone(self):
        self.assertEqual([r["kind"] for r in needs(self.dir)], ["decision"])
        status, body = self.request("/api/decisions")
        self.assertEqual((status, body["count"]), (200, 1))
        got = body["decisions"][0]
        self.assertEqual((got["id"], got["question"], got["title"], got["room"], got["card"], got["chat"]),
                         (self.row["id"], "Clear or smoked glass?", "Lantern", "lantern", None, False))
        self.assertEqual([o["text"] for o in got["options"]], ["Clear", "Smoked"])

    def test_the_phone_answers_it(self):
        status, body = self.request(f"/api/decisions/{self.row['id']}", "POST", {"choice": "a"})
        self.assertEqual((status, body), (200, {"room": "lantern", "sent": False}))
        stored = next(r for r in list_decisions(self.dir) if r["id"] == self.row["id"])
        self.assertEqual((stored["status"], stored["choice"]), ("answered", "a"))
        self.assertEqual(self.request("/api/decisions")[1]["count"], 0)


if __name__ == "__main__":
    unittest.main()
