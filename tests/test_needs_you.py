"""NEEDS-YOU.1: decisions, blocked tasks, unread replies and finished runs in one list, cleared per item."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import needs_you as ny  # noqa: E402
from board.model import new_event  # noqa: E402
from board.store import LocalStore  # noqa: E402
from decisions import ask_decision  # noqa: E402
from events import append_channel  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

ME = "claude:1a2b3c4d"


def row(key, kind, ts, changed=None, title="t"):
    return {"key": key, "kind": kind, "ts": ts, "changed": ts if changed is None else changed, "title": title,
            "detail": "", "room": None, "card": None}


class Merge(unittest.TestCase):
    def test_urgency_then_oldest_first(self):
        got = ny.merge([row("room:a", "run", 1), row("room:b", "reply", 5), row("card:c", "blocked", 9),
                        row("decision:d", "decision", 7), row("decision:e", "decision", 3),
                        row("room:f", "reply", 2)])
        self.assertEqual([r["key"] for r in got], ["decision:e", "decision:d", "card:c", "room:f", "room:b", "room:a"])

    def test_one_row_per_item_the_most_urgent_kind_and_the_newest_change(self):
        got = ny.merge([row("room:a", "run", 4, 4), row("room:a", "reply", 2, 3), row("room:a", "run", 1)])
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["kind"], got[0]["ts"], got[0]["changed"]), ("reply", 2, 4))

    def test_cleared_rows_stay_out_until_they_change(self):
        rows = [row("room:a", "reply", 2, 5), row("card:b", "blocked", 3)]
        self.assertEqual([r["key"] for r in ny.merge(rows, cleared={"room:a": 5})], ["card:b"])
        self.assertEqual([r["key"] for r in ny.merge(rows, cleared={"room:a": 4})], ["card:b", "room:a"])


class Sources(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.reg = Registry(self.dir)
        self.now = time.time()
        set_topic(self.dir, "lantern", title="Lantern room", project="lantern", status="open")
        set_topic(self.dir, "forge", title="Forge", project="forge", status="open")

    def tearDown(self):
        self._tmp.cleanup()

    def say(self, room, sender, ago, text="the glass is clear", to="user", kind="msg"):
        append_channel(self.dir, {"ts": self.now - ago, "from": sender, "to": to, "channel": room, "icon": "speech",
                                  "note": text, "kind": kind})

    def run_ended(self, room, outcome="ok", project="lantern"):
        LocalStore(self.dir).append_event(new_event("prompt", "daniel", room=room, target="claude", outcome=outcome),
                                          project=project)

    def keys(self):
        return [(r["kind"], r["key"]) for r in ny.pending(self.dir, now=self.now + 1)]

    def test_all_four_sources_in_one_list(self):
        join_topic(self.dir, "lantern", ME)
        card = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern", assignee=ME)["id"]
        asked = AgentApi(self.reg).decision_ask(ME, card, "Clear or smoked glass?", ["Clear", "Smoked"])
        stuck = self.reg.task_create("forge", "Relight the forge", topic="forge")["id"]
        self.reg.task_move(stuck, "doing")
        self.reg.task_move(stuck, "blocked")
        self.say("forge", "user", 50, "light it", to="claude:room")
        self.say("forge", "claude:room", 40, "The bellows are torn.")
        self.run_ended("forge", project="forge")
        self.say("lantern", "user", 30, "trim the wick", to="claude:room")
        self.run_ended("lantern", "error")
        got = ny.pending(self.dir, now=self.now + 1)
        self.assertEqual([(r["kind"], r["key"]) for r in got],
                         [("decision", f"decision:{asked['id']}"), ("blocked", f"card:{stuck}"),
                          ("reply", "room:forge"), ("run", "room:lantern")])
        self.assertEqual((got[0]["title"], got[0]["card"], got[0]["detail"]),
                         ("Polish the lantern glass", card, "Clear or smoked glass?"))
        self.assertEqual((got[1]["title"], got[1]["card"]), ("Relight the forge", stuck))
        self.assertEqual((got[2]["title"], got[2]["room"], got[2]["detail"]),
                         ("Forge", "forge", "The bellows are torn."))
        self.assertEqual((got[3]["title"], got[3]["detail"]), ("Lantern room", "Run failed"))

    def test_an_answered_decision_and_a_card_out_of_blocked_leave(self):
        join_topic(self.dir, "lantern", ME)
        card = self.reg.task_create("lantern", "Polish", topic="lantern", assignee=ME)["id"]
        asked = AgentApi(self.reg).decision_ask(ME, card, "Clear?", ["Yes", "No"])
        self.reg.task_move(card, "doing")
        self.reg.task_move(card, "blocked")
        self.assertEqual(len(self.keys()), 2)
        self.reg.decision_answer(asked["id"], "a")
        self.reg.task_move(card, "doing")
        self.assertEqual(self.keys(), [])

    def test_a_reply_is_read_once_daniel_writes_again(self):
        self.say("forge", "claude:room", 40, "Done.")
        self.assertEqual(self.keys(), [("reply", "room:forge")])
        self.say("forge", "user", 20, "thanks", to="claude:room")
        self.assertEqual(self.keys(), [])

    def test_lines_not_for_daniel_and_decision_lines_are_not_replies(self):
        self.say("forge", "emit:registry", 40, "moved a card", to="claude:aa")
        asked = ask_decision(self.dir, agent=ME, room="forge", question="Which tool?", options=["a=Tongs", "b=Hammer"],
                             ts=self.now - 30)
        self.assertEqual(self.keys(), [("decision", f"decision:{asked['id']}")])

    def test_a_run_before_daniels_newer_prompt_and_a_stopped_run_are_not_listed(self):
        self.run_ended("forge", "stopped", project="forge")
        self.assertEqual(self.keys(), [])
        self.run_ended("lantern")
        self.say("lantern", "user", -0.5, "again", to="claude:room")
        self.assertEqual(self.keys(), [])

    def test_old_replies_and_runs_fade(self):
        self.say("forge", "claude:room", ny.FRESH_S + 60, "ancient")
        self.assertEqual(self.keys(), [])

    def test_clear_survives_a_restart_and_the_item_comes_back_when_it_changes(self):
        self.say("forge", "claude:room", 40, "Done.")
        self.assertTrue(ny.clear(self.dir, "room:forge", now=self.now + 1))
        self.assertEqual(self.keys(), [])
        self.assertIn("room:forge", (self.dir / ny.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(ny.pending(Path(str(self.dir)), now=self.now + 1), [])
        self.say("forge", "claude:room", 10, "One more thing.")
        self.assertEqual(self.keys(), [("reply", "room:forge")])

    def test_clear_refuses_unknown_and_malformed_keys(self):
        self.assertFalse(ny.clear(self.dir, "room:forge", now=self.now))
        for key in ("", "room:", "../x", "card:" + "a" * 200, 5, None):
            with self.subTest(key=key):
                self.assertFalse(ny.valid_key(key))
                self.assertFalse(ny.clear(self.dir, key, now=self.now))
        self.assertFalse((self.dir / ny.STORE_NAME).exists())

    def test_a_broken_store_is_an_empty_one(self):
        (self.dir / ny.STORE_NAME).write_text("{not json", encoding="utf-8")
        self.say("forge", "claude:room", 40, "Done.")
        self.assertEqual(self.keys(), [("reply", "room:forge")])

    def test_stamp_moves_when_a_source_or_the_store_changes(self):
        first = ny.stamp(self.dir)
        self.say("forge", "claude:room", 40, "Done.")
        second = ny.stamp(self.dir)
        self.assertNotEqual(first, second)
        ny.clear(self.dir, "room:forge", now=self.now + 1)
        self.assertNotEqual(second, ny.stamp(self.dir))



if __name__ == "__main__":
    unittest.main()
