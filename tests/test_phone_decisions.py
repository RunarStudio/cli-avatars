"""DECIDE.1 on the phone: pending decisions are read always; with writes on, an answer from the phone closes one."""

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from decisions import list_decisions  # noqa: E402
from inbox import read_unread  # noqa: E402
from registry import task_chats as tc  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import get_topic, join_topic  # noqa: E402

ME = "claude:1a2b3c4d"
STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneDecisions(_Writes):
    def setUp(self):
        super().setUp()
        self.reg = Registry(self.dir)
        join_topic(self.dir, "lantern", ME)
        self.card = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern", assignee=ME)["id"]
        self.row = AgentApi(self.reg).decision_ask(ME, self.card, "Clear or smoked glass?", ["Clear", "Smoked"])

    def test_pending_decisions_and_the_card_count(self):
        status, body = self.request("/api/decisions")
        self.assertEqual((status, body["count"]), (200, 1))
        got = body["decisions"][0]
        self.assertEqual((got["id"], got["question"], got["title"], got["room"], got["card"], got["chat"]),
                         (self.row["id"], "Clear or smoked glass?", "Polish the lantern glass", "lantern", self.card,
                          False))
        self.assertEqual([o["text"] for o in got["options"]], ["Clear", "Smoked"])
        _status, board = self.request("/api/board")
        self.assertEqual(board["cards"][0]["decisions"], 1)

    def test_an_answer_from_the_phone_closes_the_decision(self):
        status, body = self.request(f"/api/decisions/{self.row['id']}", "POST", {"choice": "b", "text": "thin"})
        self.assertEqual((status, body), (200, {"room": "lantern", "sent": False}))
        stored = next(r for r in list_decisions(self.dir) if r["id"] == self.row["id"])
        self.assertEqual((stored["status"], stored["choice"], stored["answer"]), ("answered", "b", "thin"))
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "open")
        answers = [m["text"] for m in read_unread(self.dir, ME) if m["kind"] == "decision_answer"]
        self.assertEqual(answers, ["Smoked: thin"])
        self.assertEqual(self.request("/api/decisions")[1]["count"], 0)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())

    def test_bad_answers(self):
        path = f"/api/decisions/{self.row['id']}"
        for body in ({}, {"choice": "z"}, {"choice": "b", "room": "x"}, {"text": 5}, {"text": "   "},
                     {"text": "x" * 1001}):
            with self.subTest(body=body):
                self.assertEqual(self.request(path, "POST", body)[0], 400)
        self.assertEqual(self.request("/api/decisions/0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f", "POST",
                                      {"text": "yes"})[0], 404)
        self.assertEqual(self.request("/api/decisions/not-an-id", "POST", {"text": "yes"})[0], 404)
        self.assertEqual(self.request(path, "POST", {"text": "yes"}, csrf=False)[0], 403)
        self.assertEqual(self.request(path, "POST", {"text": "yes"})[0], 200)
        self.assertEqual(self.request(path, "POST", {"text": "again"})[0], 409)

    def test_a_task_chat_decision_is_answered_in_that_chat(self):
        (self.work / "fake-replies.json").write_text(json.dumps(["Smoked it is.\nTASK check 1"]), encoding="utf-8")
        self.reg.task_edit(self.card, checklist=[{"text": "Pick the glass", "done": False}])
        room = self.request(f"/api/cards/{self.card}/chats", "POST", {"cli": "claude"})[1]["room"]
        tc.apply_reply(self.dir, room, ["TASK ask Which frame? | Brass | Iron"])
        asked = next(r for r in list_decisions(self.dir, open_only=True) if r["room"] == room)
        self.assertTrue(self.request("/api/decisions")[1]["decisions"][-1]["chat"])
        status, body = self.request(f"/api/decisions/{asked['id']}", "POST", {"choice": "a"})
        self.assertEqual((status, body), (200, {"room": room, "sent": True}))
        self.wait_reply(room)
        stdin = json.loads((self.work / "fake-turns.jsonl").read_text().splitlines()[0])["stdin"]
        self.assertIn("Which frame? -> Daniel: Brass", stdin)
        self.assertTrue(stdin.endswith('Daniel answered your question "Which frame?": Brass'))
        for _ in range(100):
            if self.reg.task_get(self.card)["checklist"][0]["done"]:
                break
            time.sleep(0.05)
        self.assertTrue(self.reg.task_get(self.card)["checklist"][0]["done"])

    def test_the_page_has_the_badge_sheet_and_notice(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ('id="decideBtn"', 'id="decideCount"', 'id="decide"', 'id="decideRows"', 'id="ask"',
                       'id="notice"'):
            self.assertIn(needle, html)
        for needle in ('"/api/decisions"', "isSecureContext", "Notification.requestPermission", 'tone("decide")'):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)


class PhoneDecisionsOff(PhoneDecisions):
    writes = False

    def test_pending_decisions_and_the_card_count(self):
        super().test_pending_decisions_and_the_card_count()
        self.assertEqual(self.request(f"/api/decisions/{self.row['id']}", "POST", {"text": "yes"})[0], 405)
        self.assertEqual(list_decisions(self.dir, open_only=True)[0]["id"], self.row["id"])

    test_an_answer_from_the_phone_closes_the_decision = None
    test_bad_answers = None
    test_a_task_chat_decision_is_answered_in_that_chat = None


if __name__ == "__main__":
    unittest.main()
