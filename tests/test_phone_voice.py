"""PHONE-VOICE on the phone: the parse and summary reads, and the confirm going through the existing writes.

Made-up rooms, cards and decisions in a temp data dir; the fake ``claude`` never runs (a voice task chat starts no CLI).
"""

import sys
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus  # noqa: E402
from decisions import ask_decision, list_decisions  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneVoice(_Writes):
    def setUp(self):
        super().setUp()
        set_topic(self.dir, "moon-forge", title="Moon forge", project="lantern", status="open")
        set_topic(self.dir, "ember-ledger", title="Ember ledger", project="lantern", status="open")
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("lantern", "Forge the moon lantern", topic="moon-forge")
        self.reg.task_create("lantern", "Ember ledger export", topic="ember-ledger")
        self.row = ask_decision(self.dir, agent="a1b2c3d4", room="moon-forge", question="Ship the lantern on Friday?",
                                options=["a=Yes, ship", "b=No, hold it"], card=self.card["id"])

    def parse(self, said, **extra):
        query = "&".join(f"{k}={quote(str(v))}" for k, v in {"q": said, **extra}.items())
        return self.request(f"/api/voice/parse?{query}")

    def test_approve_on_the_open_decision(self):
        status, body = self.parse("approve, ship it Friday", decision=self.row["id"])
        self.assertEqual(status, 200)
        self.assertEqual(body["action"], {"kind": "answer", "verdict": "approve", "choice": "a",
                                          "text": "ship it Friday"})
        self.assertEqual(body["decision"], self.row["id"])
        self.assertTrue(body["writes"])

    def test_an_unknown_decision_makes_a_draft(self):
        status, body = self.parse("approve", decision="00000000-0000-4000-8000-000000000000")
        self.assertEqual((status, body["action"]["kind"]), (200, "draft"))

    def test_new_task_ranks_a_topic_with_alternates(self):
        status, body = self.parse("new task polish the moon lantern glass", current="ember-ledger")
        self.assertEqual(status, 200)
        self.assertEqual(body["action"], {"kind": "task", "title": "Polish the moon lantern glass", "chat": True})
        self.assertEqual(body["topics"][0], {"id": "moon-forge", "title": "Moon forge"})
        self.assertIn("ember-ledger", [t["id"] for t in body["topics"]])

    def test_reads_work_with_writes_off_but_say_so(self):
        self.writes = False
        status, body = self.parse("hello there")
        self.assertEqual((status, body["writes"]), (200, False))
        self.assertEqual(self.request("/api/voice/summary")[0], 200)

    def test_unpaired_is_refused(self):
        self.assertEqual(self.request("/api/voice/parse?q=yes", cookie=False)[0], 401)
        self.assertEqual(self.request("/api/voice/summary", cookie=False)[0], 401)

    def test_bad_ids_are_refused(self):
        self.assertEqual(self.request("/api/voice/summary?task=nope")[0], 400)
        self.assertEqual(self.request("/api/voice/summary?task=00000000-0000-4000-8000-000000000000")[0], 404)

    def test_confirmed_answer_lands_through_the_decision_route(self):
        _status, body = self.parse("approve, ship it Friday", decision=self.row["id"])
        act = body["action"]
        status, _ = self.request(f"/api/decisions/{self.row['id']}", "POST", {"choice": act["choice"], "text": act["text"]})
        self.assertEqual(status, 200)
        row = next(r for r in list_decisions(self.dir) if r["id"] == self.row["id"])
        self.assertEqual((row["status"], row["choice"]), ("answered", "a"))

    def test_confirmed_task_makes_a_card_and_chat_but_starts_no_cli(self):
        _status, body = self.parse("start a chat about the moon lantern wick")
        act, topic = body["action"], body["topics"][0]["id"]
        status, made = self.request("/api/capture", "POST", {"text": act["title"], "topic": topic, "chat": True})
        self.assertEqual(status, 200)
        self.assertTrue(made["room"].startswith("task-"))
        card = self.reg.task_get(made["id"])
        self.assertEqual((card["title"], card["topic"], card["column"]), ("The moon lantern wick", "moon-forge", "todo"))
        self.assertEqual(list(Path(self._tmp.name).rglob("fake-turns.jsonl")), [])

    def test_summary_of_a_task(self):
        store = self.reg.store
        store.put({**store.get(self.card["id"]), "summary": "done: glass cut\nnow: silver rims\nnext: test the wick",
                   "summary_at": "2026-11-25T08:00:00Z"}, actor="daniel")
        status, body = self.request(f"/api/voice/summary?task={self.card['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"line": "Forge the moon lantern. Done: glass cut. Now: silver rims. Next: test the wick.",
                                "held": False})

    def test_summary_of_what_needs_you(self):
        status, body = self.request("/api/voice/summary")
        self.assertEqual((status, body["held"]), (200, False))
        self.assertTrue(body["line"].startswith("1 thing waits on you: 1 decision"), body["line"])

    def test_focus_holds_the_summary_of_other_tasks(self):
        other = self.reg.task_create("lantern", "Glass apple orchard", topic="ember-ledger")
        self.assertTrue(focus.start(self.dir, other["id"]))
        _status, body = self.request(f"/api/voice/summary?task={self.card['id']}")
        self.assertTrue(body["held"])
        self.assertEqual(body["line"], "Held: focus is on Glass apple orchard.")
        _status, body = self.request(f"/api/voice/summary?task={other['id']}")
        self.assertFalse(body["held"])
        _status, body = self.request("/api/voice/summary")
        self.assertEqual(body["line"], "Nothing waits on you.")

    def test_the_page_has_the_mics_speech_and_a_text_fallback(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for path in ("/static/voice.js", "/static/voice.css"):
            self.assertIn(path, html)
            self.assertEqual(self.request(path)[0], 200)
        self.assertIn('id="voice"', html)
        self.assertIn('id="voiceText"', html)
        js = (STATIC / "voice.js").read_text(encoding="utf-8")
        for needle in ("webkitSpeechRecognition", "speechSynthesis", "/api/voice/parse", "/api/voice/summary",
                       '"/api/decisions/"', '"/api/capture"', "function voiceConfirm(", "function voiceMic("):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("/api/chat/", js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ("voiceRow(c)", 'voiceMic("ask")', 'voiceMic("needs")'):
            self.assertIn(needle, app)


if __name__ == "__main__":
    unittest.main()
