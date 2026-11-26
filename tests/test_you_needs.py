"""YOU-AVATAR: who needs Daniel, from needs-you rows and hook state; BODY poses reach agents that are no members."""

import unittest
from types import SimpleNamespace

from cli_avatars.app.body import TAP, SLUMP, Runs, Thresholds, states
from cli_avatars.app.you_needs import GLYPHS, Need, asker, near, who


def agent(aid, project="lantern", status="idle", **kw):
    return SimpleNamespace(agent_id=aid, project=project, status=status, parent_id=kw.get("parent"),
                           source=kw.get("source", "claude"), failed=kw.get("failed", False), last_seen=0.0)


def row(kind, room, key=None, card=None, detail=""):
    return {"key": key or f"room:{room}", "kind": kind, "room": room, "card": card, "detail": detail}


AGENTS = {"a1": agent("a1"), "b2": agent("b2"), "c3": agent("c3", project="harbour")}


class Who(unittest.TestCase):
    def test_a_decision_reaches_its_asker_without_topic_members(self):
        found = who([row("decision", "lantern", key="decision:d1")], [{"id": "lantern"}], [], AGENTS,
                    {"d1": "claude:b2"})
        self.assertEqual(set(found), {"b2"})
        self.assertEqual(found["b2"].kind, "decision")

    def test_a_reply_reaches_members_else_the_room_project(self):
        items = [row("reply", "lantern")]
        self.assertEqual(set(who(items, [{"id": "lantern", "members": ["a1"]}], [], AGENTS)), {"a1"})
        self.assertEqual(set(who(items, [], [], AGENTS)), {"a1", "b2"})
        self.assertEqual(set(who(items, [{"id": "lantern", "project": "harbour"}], [], AGENTS)), {"c3"})

    def test_a_blocked_card_reaches_its_assignee(self):
        cards = [{"id": "k1", "column": "blocked", "assignee": "c3@claude", "topic": "lantern"}]
        found = who([row("blocked", "lantern", key="card:k1", card="k1")], [], cards, AGENTS)
        self.assertEqual(set(found), {"c3"})
        self.assertTrue(found["c3"].stuck)

    def test_hook_state_alone_needs_you(self):
        agents = {"a1": agent("a1", status="blocked"), "b2": agent("b2", status="error"),
                  "c3": agent("c3", failed=True)}
        found = who([], [], [], agents)
        self.assertEqual({k: v.kind for k, v in found.items()}, {"a1": "reply", "b2": "run", "c3": "run"})
        self.assertIsNone(found["a1"].item)

    def test_most_urgent_row_wins_and_bots_and_subagents_never_bubble(self):
        agents = {**AGENTS, "s1": agent("s1", parent="a1"), "bot": agent("bot", source="bot")}
        items = [row("decision", "lantern", key="decision:d1"), row("reply", "lantern")]
        found = who(items, [], [], agents, {"d1": "a1"})
        self.assertEqual(found["a1"].kind, "decision")
        self.assertEqual(found["b2"].kind, "reply")
        self.assertNotIn("s1", found)
        self.assertNotIn("bot", found)

    def test_mail_and_couriers_are_not_bubbles(self):
        self.assertEqual(who([row("mail", "lantern"), row("courier", "lantern")], [], [], AGENTS), {})

    def test_glyphs_and_stuck(self):
        self.assertEqual(GLYPHS, {"decision": "?", "blocked": "!", "reply": "?", "run": "!"})
        self.assertTrue(Need("run", row("run", "x", detail="Run failed")).stuck)
        self.assertFalse(Need("run", row("run", "x", detail="Run finished")).stuck)
        self.assertFalse(Need("reply").stuck)

    def test_asker_and_near(self):
        self.assertEqual(asker("claude:abc"), "abc")
        self.assertEqual(asker("grok:abc"), "grok:abc")
        self.assertIsNone(asker(""))
        needs = {"a1": Need("reply"), "b2": Need("reply")}
        spots = {"a1": (3.0, 3.0), "b2": (1.0, 1.5)}
        self.assertEqual(near((1.0, 1.0), spots, needs, 1.4), "b2")
        self.assertIsNone(near((9.0, 9.0), spots, needs, 1.4))
        self.assertIsNone(near(None, spots, needs, 1.4))


class StaleRows(unittest.TestCase):
    def test_a_blocked_row_whose_card_moved_on_needs_nobody(self):
        agents = {"b2": agent("b2")}
        cards = [{"id": "k1", "column": "doing", "assignee": "b2"}]
        self.assertEqual(who([row("blocked", "lantern", key="card:k1", card="k1")], [], cards, agents), {})
        self.assertEqual(who([row("blocked", "lantern", key="card:k1", card="k1")], [], [], agents), {})


class BodyPoses(unittest.TestCase):
    def test_the_asker_taps_and_a_blocked_assignee_slumps_without_members(self):
        agents = {"a1": agent("a1"), "b2": agent("b2")}
        items = [row("decision", "lantern", key="decision:d1")]
        direct = who(items, [], [], agents, {"d1": "a1"})
        found = states(agents, [], [], items, {}, Runs(), 100.0, Thresholds(), direct)
        self.assertEqual(found.poses["a1"], TAP)
        cards = [{"id": "k1", "column": "blocked", "assignee": "b2"}]
        direct = who([row("blocked", "lantern", key="card:k1", card="k1")], [], cards, agents)
        found = states(agents, [], [], [], {}, Runs(), 100.0, Thresholds(), direct)
        self.assertEqual(found.poses["b2"], SLUMP)


if __name__ == "__main__":
    unittest.main()
