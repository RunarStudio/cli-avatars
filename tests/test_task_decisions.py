"""DECIDE.1: an agent asks Daniel a decision on a task; the task waits on him until he answers. No Tk."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars_mcp import tasks as mcp_tasks  # noqa: E402
from decisions import list_decisions  # noqa: E402
from events import EventRejected  # noqa: E402
from inbox import read_unread  # noqa: E402
from registry import task_chats as tc  # noqa: E402
from registry import task_decisions as td  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import get_topic, join_topic, set_topic, topic_messages  # noqa: E402

ME = "claude:1a2b3c4d"
OTHER = "grok:9f3c0e11"
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "lantern", title="Lantern", project="keep-demo", status="open")
        set_topic(self.dir, "gate", title="Gate", project="keep-demo", status="open")
        join_topic(self.dir, "lantern", ME)
        self.reg = Registry(self.dir)
        self.api = AgentApi(self.reg)
        self.mine = self.reg.task_create("keep-demo", "Polish the lantern glass", topic="lantern")["id"]
        self.reg.task_assign(self.mine, ME)
        self.loose = self.reg.task_create("keep-demo", "Sweep the hall", topic="lantern")["id"]
        self.theirs = self.reg.task_create("keep-demo", "Mend the banner", topic="lantern")["id"]
        self.reg.task_assign(self.theirs, OTHER)
        self.foreign = self.reg.task_create("keep-demo", "Oil the gate", topic="gate")["id"]

    def tearDown(self):
        self._tmp.cleanup()

    def ask(self, card=None, question="Clear or smoked glass?", options=("Clear", "Smoked")):
        return self.api.decision_ask(ME, card or self.mine, question, list(options) if options else None)


class Raise(_Base):
    def test_an_agent_asks_on_its_task_and_the_task_waits_on_daniel(self):
        row = self.ask()
        self.assertEqual((row["status"], row["card"], row["from"], row["room"]), ("open", self.mine, ME, "lantern"))
        self.assertEqual(row["options"], [{"letter": "a", "text": "Clear"}, {"letter": "b", "text": "Smoked"}])
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "waiting_on_user")
        pending = td.pending(self.dir)
        self.assertEqual([(p["id"], p["title"], p["topic"]) for p in pending],
                         [(row["id"], "Polish the lantern glass", "lantern")])
        self.assertEqual(td.open_by_card(self.dir), {self.mine: 1})
        history = self.reg.task_get(self.mine)["history"]
        self.assertEqual((history[-1]["kind"], history[-1]["actor"], history[-1]["via"]), ("decision", ME, "mcp"))
        self.assertIn("Clear or smoked glass?", history[-1]["text"])

    def test_an_unassigned_task_in_its_topic_is_open_to_the_agent_and_options_are_optional(self):
        row = self.ask(self.loose, "Which broom?", None)
        self.assertEqual((row["card"], row["options"]), (self.loose, []))

    def test_text_is_redacted_path_scrubbed_and_capped(self):
        row = self.ask(question=f"Use {TOKEN} from /home/someone/keys.txt? " + "x" * 600,
                       options=(f"Yes {TOKEN}", "No"))
        self.assertNotIn(TOKEN, row["question"])
        self.assertNotIn("/home/someone", row["question"])
        self.assertLessEqual(len(row["question"]), 240)
        self.assertNotIn(TOKEN, row["options"][0]["text"])
        with self.assertRaises(EventRejected) as caught:
            self.ask(options=[f"choice {n}" for n in range(7)])
        self.assertEqual(caught.exception.reason, "schema")
        for bad in ("", "   ", None, 7):
            with self.subTest(question=bad), self.assertRaises(EventRejected):
                self.api.decision_ask(ME, self.mine, bad)
        with self.assertRaises(EventRejected):
            self.ask(options=["Clear", ""])

    def test_another_agents_or_a_foreign_task_is_refused_and_nothing_is_written(self):
        cases = ((ME, self.theirs, "not_owner"), (ME, self.foreign, "not_owner"), ("daniel", self.mine, "not_agent"),
                 ("user", self.mine, "not_agent"), (ME, "0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f", "missing"))
        for agent, card, reason in cases:
            with self.subTest(agent=agent, card=card), self.assertRaises(EventRejected) as caught:
                self.api.decision_ask(agent, card, "Mine now?")
            self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(list_decisions(self.dir), [])
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "open")
        self.assertEqual(get_topic(self.dir, "gate")["status"], "open")

    def test_a_done_archived_or_topicless_task_is_not_asked_on(self):
        self.reg.task_move(self.loose, "done")
        bare = self.reg.task_create("keep-demo", "No room", assignee=ME)["id"]
        gone = self.reg.task_create("keep-demo", "Old", topic="lantern", assignee=ME)["id"]
        self.reg.task_archive(gone)
        for card in (self.loose, bare, gone):
            with self.subTest(card=card), self.assertRaises(EventRejected) as caught:
                self.ask(card)
            self.assertEqual(caught.exception.reason, "not_allowed")
        self.assertEqual(list_decisions(self.dir), [])

    def test_a_done_topic_stays_done(self):
        set_topic(self.dir, "lantern", status="done")
        self.ask()
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "done")

    def test_ten_asks_an_hour(self):
        for n in range(10):
            self.ask(question=f"Question {n}?")
        with self.assertRaises(EventRejected) as caught:
            self.ask(question="One more?")
        self.assertEqual(caught.exception.reason, "rate_limited")


class Answer(_Base):
    def test_a_text_answer_reaches_the_agent_and_clears_the_waiting(self):
        row = self.ask()
        answer = self.reg.decision_answer(row["id"], text="Smoked, but thin")
        self.assertEqual((answer["kind"], answer["to"], answer["text"]), ("decision_answer", [ME], "Smoked, but thin"))
        inbox = [m for m in read_unread(self.dir, ME) if m["kind"] == "decision_answer"]
        self.assertEqual([(m["text"], m["decision_id"]) for m in inbox], [("Smoked, but thin", row["id"])])
        stored = next(r for r in list_decisions(self.dir) if r["id"] == row["id"])
        self.assertEqual((stored["status"], stored["answer"], stored["card"]), ("answered", "Smoked, but thin", self.mine))
        self.assertIsInstance(stored["answered_ts"], float)
        self.assertEqual(td.pending(self.dir), [])
        self.assertEqual(td.open_by_card(self.dir), {})
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "open")
        notes = [m for m in topic_messages(self.dir, "lantern") if m.get("from") == "user"]
        self.assertIn("Smoked, but thin", notes[-1]["text"])
        history = self.reg.task_get(self.mine)["history"]
        self.assertEqual((history[-1]["kind"], history[-1]["actor"]), ("decision", "daniel"))
        self.assertIn("Smoked, but thin", history[-1]["text"])
        with self.assertRaises(EventRejected) as caught:
            self.reg.decision_answer(row["id"], text="Again")
        self.assertEqual(caught.exception.reason, "answered")

    def test_an_option_answer_and_bad_answers(self):
        row = self.ask()
        for kwargs in ({}, {"choice": "c"}, {"choice": "ab"}, {"text": "  "}):
            with self.subTest(kwargs=kwargs), self.assertRaises(EventRejected):
                self.reg.decision_answer(row["id"], **kwargs)
        answer = self.reg.decision_answer(row["id"], choice="b")
        self.assertEqual(answer["text"], "Smoked")
        stored = next(r for r in list_decisions(self.dir) if r["id"] == row["id"])
        self.assertEqual(stored["choice"], "b")

    def test_an_option_with_a_note(self):
        row = self.ask()
        answer = self.reg.decision_answer(row["id"], choice="a", text="keep the old frame")
        self.assertEqual(answer["text"], "Clear: keep the old frame")

    def test_the_task_waits_while_another_decision_in_its_topic_is_open(self):
        first, second = self.ask(), self.ask(self.loose, "Which broom?", None)
        self.reg.decision_answer(first["id"], choice="a")
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "waiting_on_user")
        self.reg.decision_answer(second["id"], text="The long one")
        self.assertEqual(get_topic(self.dir, "lantern")["status"], "open")


class Paths(_Base):
    def test_the_mcp_tool_goes_through_the_agent_api(self):
        row = mcp_tasks.task_decide(ME, self.mine, "Clear or smoked?", ["Clear", "Smoked"], registry=self.reg)
        self.assertEqual((row["card"], row["from"]), (self.mine, ME))
        with self.assertRaises(EventRejected) as caught:
            mcp_tasks.task_decide(ME, self.theirs, "Mine?", registry=self.reg)
        self.assertEqual(caught.exception.reason, "not_owner")
        with self.assertRaises(EventRejected) as caught:
            mcp_tasks.task_decide(ME, self.mine, "x" * 5000, registry=self.reg)
        self.assertEqual(caught.exception.reason, "schema")

    def test_a_task_chat_asks_with_a_task_line_in_its_own_room(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("a CLI process was started")):
            _card, chat = tc.start_chat(self.reg, self.mine, "claude")
        room = chat["room"]
        done = tc.apply_reply(self.dir, room, ["Two ways.\nTASK ask Clear or smoked glass? | Clear | Smoked"])
        self.assertEqual(done, ["asked Daniel"])
        row = td.pending(self.dir)[0]
        self.assertEqual((row["room"], row["from"], row["card"]), (room, f"claude:{room}", self.mine))
        self.assertEqual([o["text"] for o in row["options"]], ["Clear", "Smoked"])
        context = tc.context(self.dir, self.reg.task_get(self.mine))
        self.assertIn("Clear or smoked glass?", context)
        self.assertIn("waiting on Daniel", context)
        self.reg.decision_answer(row["id"], choice="b")
        context = tc.context(self.dir, self.reg.task_get(self.mine))
        self.assertIn("Daniel: Smoked", context)
        other = tc.start_chat(self.reg, self.loose, "claude")[1]["room"]
        self.assertEqual(tc.apply_reply(self.dir, other, ["TASK ask Mine?"]), ["asked Daniel"])
        self.assertEqual(td.pending(self.dir)[0]["card"], self.loose)

    def test_the_hook_and_phone_rows_name_the_card(self):
        row = self.ask()
        public = td.public(td.pending(self.dir)[0])
        self.assertEqual(set(public), {"id", "ts", "from", "room", "question", "options", "card", "title", "topic",
                                       "project", "column", "chat"})
        self.assertEqual((public["id"], public["chat"]), (row["id"], False))


if __name__ == "__main__":
    unittest.main()
