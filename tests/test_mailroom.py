"""MAILROOM: new thoughts, messages and hook questions land in one store; a local sorter proposes a topic, a task
chat and a draft decision; nothing is filed until Daniel approves. Bounce sends a letter to Unsorted, a second
bounce drops it. The phone routes sit behind ``web.allow_writes`` and the CSRF header.

The sorter is local code: no process, no socket.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus  # noqa: E402
import mailroom  # noqa: E402
import needs_you  # noqa: E402
from _no_side_effects import refuse  # noqa: E402
from decisions import list_decisions  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

AGENT = "claude:5e6f7a8b"
STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


def _line(directory, room, sender, text, to="user", kind="msg", ts=None):
    entry = {"ts": time.time() if ts is None else ts, "from": sender, "to": to, "channel": room, "icon": "speech",
             "note": text}
    if kind:
        entry["kind"] = kind
    append_channel(Path(directory), entry)


def seed(directory: Path) -> Registry:
    set_topic(directory, "west-wing", title="West wing", project="keep", status="open")
    set_topic(directory, "orchard", title="Orchard", project="garden", status="open")
    reg = Registry(directory)
    reg.task_create("keep", "Light the torches", topic="west-wing")
    reg.task_create("garden", "Prune the apple rows", topic="orchard")
    return reg


def all_cards(directory: Path) -> list[dict]:
    reg = Registry(directory)
    return reg.task_list("keep") + reg.task_list("garden")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.reg = seed(self.dir)
        mailroom.ingest(self.dir, now=time.time() - 60)

    def tearDown(self):
        self._tmp.cleanup()


class Store(Base):
    def test_a_thought_lands_unfiled_and_survives_a_restart(self):
        before = len(all_cards(self.dir))
        item = mailroom.post(self.dir, "Buy oil for the torches")
        self.assertEqual(len(all_cards(self.dir)), before)
        raw = json.loads((self.dir / mailroom.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual([i["id"] for i in raw["items"]], [item["id"]])
        again = mailroom.public(self.dir)
        self.assertEqual([i["text"] for i in again["items"]], ["Buy oil for the torches"])
        self.assertEqual((again["count"], item["source"], item["state"]), (1, "capture", "new"))

    def test_empty_thoughts_are_refused(self):
        for text in ("", "   ", None, 5):
            with self.subTest(text=text):
                self.assertIsNone(mailroom.post(self.dir, text))
        self.assertEqual(mailroom.public(self.dir)["count"], 0)

    def test_first_start_takes_no_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            _line(tmp, "orchard", AGENT, "Old note from last week?", ts=time.time() - 3600)
            self.assertEqual(mailroom.ingest(tmp), [])
            self.assertEqual(mailroom.public(tmp)["count"], 0)


class Sources(Base):
    def test_a_message_to_daniel_lands_once(self):
        _line(self.dir, "orchard", AGENT, "The apple rows need a new ladder.")
        got = mailroom.ingest(self.dir)
        self.assertEqual([(i["source"], i["from"], i["room"]) for i in got], [("message", AGENT, "orchard")])
        self.assertEqual(mailroom.ingest(self.dir), [])
        self.assertEqual(mailroom.public(self.dir)["count"], 1)

    def test_a_hook_question_lands_and_a_hook_status_note_does_not(self):
        _line(self.dir, "west-wing", AGENT, "I lit four torches. Should I light the cellar ones too?", to=AGENT,
              kind=None)
        _line(self.dir, "west-wing", AGENT, "Lit four torches.", to=AGENT, kind=None)
        got = mailroom.ingest(self.dir)
        self.assertEqual([i["source"] for i in got], ["hook"])

    def test_task_chats_his_own_lines_and_live_conversations_stay_out(self):
        card = self.reg.task_create("keep", "Mend the gate", topic="west-wing")["id"]
        _line(self.dir, f"task-{card[:8]}-1", AGENT, "Gate mended.")
        _line(self.dir, "orchard", "user", "Hello there")
        _line(self.dir, "orchard", AGENT, "Hi! Want me to start?")
        _line(self.dir, "west-wing", "emit:board", "Chat on task 1234: x")
        self.assertEqual(mailroom.ingest(self.dir), [])


class Sorter(Base):
    def test_topic_comes_from_the_capture_ranker(self):
        item = mailroom.post(self.dir, "The apple rows need water")
        self.assertEqual(item["topic"], "orchard")
        item = mailroom.post(self.dir, "Torches smoke in the west wing")
        self.assertEqual(item["topic"], "west-wing")

    def test_a_question_gets_a_draft_decision_and_work_gets_a_chat(self):
        asked = mailroom.post(self.dir, "Brass or iron hinges for the orchard gate?")
        self.assertEqual(asked["draft"], "Brass or iron hinges for the orchard gate?")
        self.assertFalse(asked["chat"])
        work = mailroom.post(self.dir, "Fix the leaking orchard well")
        self.assertTrue(work["chat"])
        self.assertEqual(work["draft"], "")

    def test_a_message_room_is_the_fallback_topic(self):
        _line(self.dir, "orchard", AGENT, "zzz qqq")
        (item,) = mailroom.ingest(self.dir)
        self.assertEqual(item["topic"], "orchard")

    def test_sorting_is_local(self):
        with patch("subprocess.Popen", refuse), patch("socket.socket", refuse):
            _line(self.dir, "orchard", AGENT, "Should we graft the pears?")
            first = mailroom.ingest(self.dir)
            item = mailroom.post(self.dir, "Fix the torches")
        self.assertEqual((first[0]["topic"], item["topic"]), ("orchard", "west-wing"))


class Approve(Base):
    def test_approve_files_one_card_as_daniel_and_leaves_the_mailroom(self):
        item = mailroom.post(self.dir, "Oil the west wing hinges")
        before = len(all_cards(self.dir))
        out = mailroom.approve(self.dir, item["id"])
        self.assertEqual(len(all_cards(self.dir)), before + 1)
        card = out["card"]
        self.assertEqual((card["title"], card["topic"], card["column"]), ("Oil the west wing hinges", "west-wing", "todo"))
        self.assertEqual(card["history"][0]["actor"], "daniel")
        self.assertIsNone(out["room"])
        self.assertEqual(mailroom.public(self.dir)["count"], 0)
        self.assertIsNone(mailroom.approve(self.dir, item["id"]))

    def test_approve_opens_the_task_chat_when_proposed(self):
        item = mailroom.post(self.dir, "Fix the leaking orchard well")
        out = mailroom.approve(self.dir, item["id"])
        fresh = Registry(self.dir).task_get(out["card"]["id"])
        self.assertEqual([c["room"] for c in fresh["chats"]], [out["room"]])

    def test_approve_asks_the_drafted_decision_on_the_card(self):
        _line(self.dir, "orchard", AGENT, "Brass or iron hinges for the orchard gate?")
        (item,) = mailroom.ingest(self.dir)
        out = mailroom.approve(self.dir, item["id"])
        (row,) = list_decisions(self.dir, open_only=True)
        self.assertEqual((row["card"], row["from"], row["question"]),
                         (out["card"]["id"], AGENT, "Brass or iron hinges for the orchard gate?"))

    def test_edit_topic_before_approve(self):
        item = mailroom.post(self.dir, "Oil the west wing hinges")
        self.assertFalse(mailroom.retopic(self.dir, item["id"], "nowhere"))
        self.assertFalse(mailroom.retopic(self.dir, item["id"], "task-0123abcd-1"))
        self.assertTrue(mailroom.retopic(self.dir, item["id"], "orchard"))
        self.assertEqual(mailroom.public(self.dir)["items"][0]["topic"], "orchard")
        out = mailroom.approve(self.dir, item["id"])
        self.assertEqual(out["card"]["topic"], "orchard")

    def test_bounce_goes_to_unsorted_then_drops(self):
        item = mailroom.post(self.dir, "Oil the west wing hinges")
        self.assertEqual(mailroom.bounce(self.dir, item["id"]), "unsorted")
        state = mailroom.public(self.dir)
        self.assertEqual((state["count"], [i["id"] for i in state["unsorted"]]), (0, [item["id"]]))
        self.assertEqual(mailroom.bounce(self.dir, item["id"]), "dropped")
        state = mailroom.public(self.dir)
        self.assertEqual((state["count"], state["unsorted"]), (0, []))
        self.assertIsNone(mailroom.bounce(self.dir, item["id"]))

    def test_an_unsorted_letter_can_still_be_filed(self):
        item = mailroom.post(self.dir, "Oil the west wing hinges")
        mailroom.bounce(self.dir, item["id"])
        self.assertIsNotNone(mailroom.approve(self.dir, item["id"]))
        self.assertEqual(mailroom.public(self.dir)["unsorted"], [])

    def test_a_failed_filing_keeps_the_letter(self):
        item = mailroom.post(self.dir, "Oil the west wing hinges")
        with patch("registry.capture.capture", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                mailroom.approve(self.dir, item["id"])
        self.assertEqual(mailroom.public(self.dir)["count"], 1)


class Focus(Base):
    def test_letters_wait_while_another_task_is_in_focus(self):
        card = self.reg.task_list("keep")[0]["id"]
        focus.start(self.dir, card, now=time.time() - 30)
        mailroom.post(self.dir, "The apple rows need water")
        mailroom.post(self.dir, "Torches smoke in the west wing")
        state = mailroom.public(self.dir)
        self.assertEqual(([i["topic"] for i in state["items"]], state["held"]), (["west-wing"], 1))
        focus.leave(self.dir)
        state = mailroom.public(self.dir)
        self.assertEqual((state["count"], state["held"]), (2, 0))


class NeedsYou(Base):
    def test_one_mail_row_counts_the_letters(self):
        self.assertFalse([r for r in needs_you.pending(self.dir) if r["kind"] == "mail"])
        mailroom.post(self.dir, "Buy oil")
        mailroom.post(self.dir, "Fix the gate")
        (row,) = [r for r in needs_you.pending(self.dir) if r["kind"] == "mail"]
        self.assertEqual((row["key"], row["title"], row["detail"]), ("mail:mailroom", "Mailroom", "2 letters to sort"))
        self.assertTrue(needs_you.clear(self.dir, "mail:mailroom"))
        self.assertFalse([r for r in needs_you.pending(self.dir) if r["kind"] == "mail"])


class _PhoneMail(_Writes):
    def setUp(self):
        super().setUp()
        set_topic(self.dir, "orchard", title="Orchard", project="garden", status="open")
        Registry(self.dir).task_create("garden", "Prune the apple rows", topic="orchard")
        mailroom.ingest(self.dir, now=time.time() - 60)


class PhoneMail(_PhoneMail):
    def test_list_post_retopic_approve_bounce(self):
        status, out = self.request("/api/mailroom", "POST", {"text": "Water the apple rows"})
        self.assertEqual(status, 200, out)
        first = out["id"]
        self.request("/api/mailroom", "POST", {"text": "Trim the lantern wick"})
        status, out = self.request("/api/mailroom")
        self.assertEqual((status, out["count"], out["writes"]), (200, 2, True))
        self.assertIn("orchard", [t["id"] for t in out["topics"]])
        second = next(i["id"] for i in out["items"] if i["id"] != first)
        status, _out = self.request(f"/api/mailroom/{second}/topic", "POST", {"topic": "orchard"})
        self.assertEqual(status, 200)
        status, out = self.request(f"/api/mailroom/{second}/approve", "POST", {})
        self.assertEqual(status, 200, out)
        self.assertEqual(Registry(self.dir).task_get(out["id"])["topic"], "orchard")
        status, out = self.request(f"/api/mailroom/{first}/bounce", "POST", {})
        self.assertEqual((status, out["now"]), (200, "unsorted"))
        status, out = self.request("/api/mailroom")
        self.assertEqual((out["count"], len(out["unsorted"])), (0, 1))

    def test_bad_writes(self):
        for path, body, want in (("/api/mailroom", {"text": "  "}, 400), ("/api/mailroom", {"text": 3}, 400),
                                 ("/api/mailroom", {"text": "x", "more": 1}, 400),
                                 ("/api/mailroom/0123456789abcdef/approve", {}, 404),
                                 ("/api/mailroom/../approve", {}, 400),
                                 ("/api/mailroom/0123456789abcdef/topic", {"topic": "../x"}, 400)):
            status, _out = self.request(path, "POST", body)
            self.assertEqual(status, want, (path, body))

    def test_page_ships_the_mailroom_and_sse_tells_it(self):
        import http.client

        from webui import auth

        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for needle in ('id="mailBtn"', 'id="mail"', 'data-mode="mail"', "/static/mailroom.js", "/static/mailroom.css"):
            self.assertIn(needle, html)
        for path in ("/static/mailroom.js", "/static/mailroom.css"):
            self.assertEqual(self.request(path)[0], 200, path)
        self.assertIn('addEventListener("mailroom"', (STATIC / "app.js").read_text(encoding="utf-8"))
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        resp.fp.readline()
        time.sleep(0.2)
        mailroom.post(self.dir, "Water the apple rows")
        seen, deadline = b"", time.time() + 4
        while time.time() < deadline and b"event: mailroom" not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b"event: mailroom", seen)

    def test_csrf_needed(self):
        status, _out = self.request("/api/mailroom", "POST", {"text": "x"}, csrf=False)
        self.assertEqual(status, 403)
        self.assertEqual(mailroom.public(self.dir)["count"], 0)


class PhoneMailOff(_PhoneMail):
    writes = False

    def test_read_only_when_writes_are_off(self):
        mailroom.post(self.dir, "Water the apple rows")
        status, out = self.request("/api/mailroom")
        self.assertEqual((status, out["count"], out["writes"]), (200, 1, False))
        item = out["items"][0]["id"]
        status, _out = self.request(f"/api/mailroom/{item}/approve", "POST", {})
        self.assertEqual(status, 405)
        self.assertEqual(mailroom.public(self.dir)["count"], 1)


if __name__ == "__main__":
    unittest.main()
